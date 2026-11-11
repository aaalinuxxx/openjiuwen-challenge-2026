"""Experimental full-text scope gate; not a general natural-language parser."""
import csv
import re
from harness.agents.join_plans import solve_join_plan_task
from harness.agents.multi_csv import describe_csv, select_csv_inputs, solve_multi_csv_task

# Deliberately narrow grammar. Fullmatch is essential: no unparsed remainder.
# Identifiers and quoted literal contents retain their original case.
IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
PATTERN = re.compile(
    rf"Read (?P<left>{IDENT})\.csv and (?P<right>{IDENT})\.csv\. "
    rf"(?P<join>Inner|Left) join (?P<lkfile>{IDENT})\.(?P<lk>{IDENT}) "
    rf"to (?P<rkfile>{IDENT})\.(?P<rk>{IDENT}) using exact string keys\. "
    rf"Sum (?P<afile>{IDENT})\.(?P<acol>{IDENT}) for all resulting pairs"
    rf"(?: where (?P<ffile>{IDENT})\.(?P<fcol>{IDENT}) equals '(?P<literal>[^'\r\n]*)')?\. "
    r"Preserve every matching pair, including duplicates\."
    r"(?P<missing> Missing right values contribute zero\.)? Print the exact sum\.",
    re.IGNORECASE,
)


def parse_join_scope(instruction):
    match = PATTERN.fullmatch(instruction.strip())
    if match is None:
        return None
    g = match.groupdict()
    if g['left'] == g['right'] or g['lkfile'] != g['left'] or g['rkfile'] != g['right']:
        return None
    sides = {g['left']: 'left', g['right']: 'right'}
    if g['afile'] not in sides or (g['ffile'] is not None and g['ffile'] not in sides):
        return None
    kind = g['join'].lower()
    if bool(g['missing']) != (kind == 'left'):
        return None
    return dict(left=g['left']+'.csv', right=g['right']+'.csv',
                left_key=g['lk'], right_key=g['rk'], join=kind,
                filter=None if g['ffile'] is None else dict(side=sides[g['ffile']], column=g['fcol'], equals=g['literal']),
                aggregate=dict(op='sum', side=sides[g['afile']], column=g['acol']))


def join_scope_route(workspace, instruction):
    plan = parse_join_scope(instruction)
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


async def solve_join_scope_task(ctx, bridge):
    route = join_scope_route(ctx.workspace_dir, ctx.instruction)
    # Keep both existing solvers unchanged. The plan returned by parse_join_scope
    # is used for scope/schema checks only, not as a substitute API answer.
    # Representability does NOT certify that the model will generate that plan.
    solver = solve_join_plan_task if route == 'json_plan' else solve_multi_csv_task
    result = await solver(ctx, bridge)
    result.notes = 'Full-text scope route: ' + route + '. ' + result.notes
    return result
