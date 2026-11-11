"""Two bounded full-text join paraphrases, retaining the original scope grammar."""
import csv
import re
from harness.agents.join_scope import IDENT, parse_join_scope
from harness.agents.join_plans import solve_join_plan_task
from harness.agents.multi_csv import describe_csv, select_csv_inputs, solve_multi_csv_task

SHARED_KEY = re.compile(
    rf"From (?P<left>{IDENT})\.csv and (?P<right>{IDENT})\.csv, "
    rf"keep every pair with identical (?P<key>{IDENT}) strings and "
    rf"(?P<ffile>{IDENT})\.(?P<fcol>{IDENT}) equal to '(?P<literal>[^'\r\n]*)'\. "
    rf"Add (?P<afile>{IDENT})\.(?P<acol>{IDENT}) across those pairs\. "
    r"Duplicate rows must contribute repeatedly\. Return the sum as a number\.", re.IGNORECASE)
QUALIFIED_KEYS = re.compile(
    rf"Using (?P<left>{IDENT})\.csv and (?P<right>{IDENT})\.csv, "
    rf"match every (?P<lkfile>{IDENT})\.(?P<lk>{IDENT}) with every "
    rf"(?P<rkfile>{IDENT})\.(?P<rk>{IDENT}) as exact strings\. "
    rf"Keep only pairs where (?P<ffile>{IDENT})\.(?P<fcol>{IDENT}) is '(?P<literal>[^'\r\n]*)'\. "
    rf"Total (?P<afile>{IDENT})\.(?P<acol>{IDENT}) over all retained pairs, "
    r"counting duplicate rows separately\. Output only the numeric sum\.", re.IGNORECASE)


def parse_join_scope_v2(instruction):
    original = parse_join_scope(instruction)
    if original is not None:
        return original
    for pattern in (SHARED_KEY, QUALIFIED_KEYS):
        match = pattern.fullmatch(instruction.strip())
        if match is None:
            continue
        g = match.groupdict()
        if g['left'] == g['right']:
            return None
        sides = {g['left']: 'left', g['right']: 'right'}
        if g['ffile'] not in sides or g['afile'] not in sides:
            return None
        if pattern is QUALIFIED_KEYS:
            if g['lkfile'] != g['left'] or g['rkfile'] != g['right']:
                return None
            lk, rk = g['lk'], g['rk']
        else:
            lk = rk = g['key']
        return dict(left=g['left']+'.csv', right=g['right']+'.csv',
                    left_key=lk, right_key=rk, join='inner',
                    filter=dict(side=sides[g['ffile']], column=g['fcol'], equals=g['literal']),
                    aggregate=dict(op='sum', side=sides[g['afile']], column=g['acol']))
    return None


def join_scope_v2_route(workspace, instruction):
    plan = parse_join_scope_v2(instruction)
    if plan is None:
        return 'python'
    selected = select_csv_inputs(workspace, instruction)
    if selected is None or {p.name for p in selected} != {plan['left'], plan['right']}:
        return 'python'
    try:
        schemas = {p.name: describe_csv(p)['columns'] for p in selected}
    except (OSError, UnicodeError, csv.Error, ValueError):
        return 'python'
    for side in ('left', 'right'):
        if plan[side+'_key'] not in schemas[plan[side]]:
            return 'python'
    for field in ('aggregate', 'filter'):
        clause = plan[field]
        if clause is not None and clause['column'] not in schemas[plan[clause['side']]]:
            return 'python'
    return 'json_plan'


async def solve_join_scope_v2_task(ctx, bridge):
    route = join_scope_v2_route(ctx.workspace_dir, ctx.instruction)
    solver = solve_join_plan_task if route == 'json_plan' else solve_multi_csv_task
    result = await solver(ctx, bridge)
    result.notes = 'Full-text scope v2 route: ' + route + '. ' + result.notes
    return result
