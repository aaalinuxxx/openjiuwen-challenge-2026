"""Experimental typed equality OR absent-right predicate, preserving all pairs."""
import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re
from harness.config import SolveResult
from harness.agents.calculation_plans import decimal_text
from harness.agents.join_plans import _keys, _read
from harness.agents.join_scope import IDENT
from harness.agents.local_join import local_join_route, solve_local_join_task
from harness.agents.multi_csv import describe_csv, select_csv_inputs

def execute_join_or_plan(plan, selected, max_pairs=1000000):
    if not isinstance(plan, dict) or not isinstance(plan.get('filter'), dict) or plan['filter'].get('op') != 'eq_or_unmatched':
        raise ValueError('Expected explicit eq_or_unmatched predicate')
    if plan.get('join') != 'left' or plan['filter'].get('side') != 'right':
        raise ValueError('OR unmatched requires left join and right equality')
    _keys(plan, ("left","right","left_key","right_key","join","filter","aggregate"))
    for field in ("left","right","left_key","right_key","join"):
        if not isinstance(plan[field], str) or not plan[field]:
            raise ValueError("Expected nonempty string")
    files = {p.name:p for p in selected}
    if plan["left"] == plan["right"] or set((plan["left"],plan["right"])) != set(files) or len(files) != 2:
        raise ValueError("Plan must use exactly the selected files")
    if plan["join"] not in ("inner","left","anti"):
        raise ValueError("Unsupported join")
    columns, rows = {}, {}
    for side in ("left","right"):
        columns[side], rows[side] = _read(files[plan[side]])
        key = plan[side+"_key"]
        if key not in columns[side] or any(row[key] == "" for row in rows[side]):
            raise ValueError("Missing key or ambiguous empty key")
    filt = plan["filter"]
    if filt is not None:
        _keys(filt, ("op","side","column","equals"))
        if (not isinstance(filt["side"],str) or filt["side"] not in columns
                or not isinstance(filt["column"],str) or filt["column"] not in columns[filt["side"]]
                or not isinstance(filt["equals"],str)):
            raise ValueError("Invalid equality filter")
        if plan["join"] == "anti" and filt["side"] == "right":
            raise ValueError("Anti join has no right-side result row")
    aggregate = plan["aggregate"]
    _keys(aggregate, ("op","side","column"))
    if aggregate["op"] == "count":
        if aggregate["side"] is not None or aggregate["column"] is not None:
            raise ValueError("Row count cannot specify a value column")
    elif aggregate["op"] == "sum":
        if (not isinstance(aggregate["side"],str) or aggregate["side"] not in columns
                or not isinstance(aggregate["column"],str) or aggregate["column"] not in columns[aggregate["side"]]):
            raise ValueError("Invalid sum column")
        if plan["join"] == "anti" and aggregate["side"] == "right":
            raise ValueError("Anti join has no right-side values")
    else:
        raise ValueError("Unsupported aggregate")
    index = defaultdict(list)
    for row in rows["right"]:
        index[row[plan["right_key"]]].append(row)
    total, processed = Fraction(0), 0
    for left in rows["left"]:
        matches = index.get(left[plan["left_key"]], [])
        if plan["join"] == "anti":
            if matches:
                continue
            matches = (None,)
        elif not matches and plan["join"] == "left":
            matches = (None,)
        for right in matches:
            processed += 1
            if processed > max_pairs:
                raise ValueError("Join pair limit exceeded")
            pair = {"left":left,"right":right}
            if filt is not None:
                row = pair[filt["side"]]
                if row is not None and row[filt["column"]] != filt["equals"]:
                    continue
            if aggregate["op"] == "count":
                total += 1
                continue
            row = pair[aggregate["side"]]
            if row is None:
                continue
            try:
                value = Decimal(row[aggregate["column"]])
            except InvalidOperation as error:
                raise ValueError("Invalid numeric value") from error
            if not value.is_finite():
                raise ValueError("Nonfinite numeric value")
            total += Fraction(value)
    return decimal_text(total)

CANONICAL_OR = re.compile(
    rf"Read (?P<left>{IDENT})\.csv and (?P<right>{IDENT})\.csv\. "
    rf"Left join (?P<lkfile>{IDENT})\.(?P<lk>{IDENT}) to (?P<rkfile>{IDENT})\.(?P<rk>{IDENT}) using exact string keys\. "
    rf"Sum (?P<afile>{IDENT})\.(?P<acol>{IDENT}) for all resulting pairs where "
    rf"(?P<ffile>{IDENT})\.(?P<fcol>{IDENT}) equals '(?P<literal>[^'\r\n]*)' OR there is no matching right row\. "
    r"Preserve every matching pair, including duplicates\. Print the exact sum\.", re.IGNORECASE)
KNOWN_OR = re.compile(
    rf"Using (?P<left>{IDENT})\.csv and (?P<right>{IDENT})\.csv, match every "
    rf"(?P<lkfile>{IDENT})\.(?P<lk>{IDENT}) with every (?P<rkfile>{IDENT})\.(?P<rk>{IDENT}) as exact strings\. "
    rf"Keep only pairs where (?P<ffile>{IDENT})\.(?P<fcol>{IDENT}) is '(?P<literal>[^'\r\n]*)' OR there is no matching (?P<missingfile>{IDENT}) row\. "
    rf"Total (?P<afile>{IDENT})\.(?P<acol>{IDENT}) over all retained pairs, counting duplicate rows separately\. "
    rf"Also include (?P<included>{IDENT}) without a matching label\. Output only the numeric sum\.", re.IGNORECASE)


def parse_join_or_scope(instruction):
    for pattern in (CANONICAL_OR, KNOWN_OR):
        match=pattern.fullmatch(instruction.strip())
        if match is None: continue
        g=match.groupdict()
        if (g['left']==g['right'] or g['lkfile']!=g['left'] or g['rkfile']!=g['right']
                or g['ffile']!=g['right'] or g['afile']!=g['left']):
            return None
        if pattern is KNOWN_OR and (g['missingfile']!=g['right'] or g['included']!=g['left']):
            return None
        return dict(left=g['left']+'.csv',right=g['right']+'.csv',left_key=g['lk'],right_key=g['rk'],join='left',
                    filter=dict(op='eq_or_unmatched',side='right',column=g['fcol'],equals=g['literal']),
                    aggregate=dict(op='sum',side='left',column=g['acol']))
    return None


def join_or_route(workspace,instruction):
    plan=parse_join_or_scope(instruction)
    if plan is not None:
        selected=select_csv_inputs(workspace,instruction)
        if selected is not None and {p.name for p in selected}=={plan['left'],plan['right']}:
            try:
                columns={p.name:describe_csv(p)['columns'] for p in selected}
                if (plan['left_key'] in columns[plan['left']] and plan['right_key'] in columns[plan['right']]
                    and plan['aggregate']['column'] in columns[plan['left']]
                    and plan['filter']['column'] in columns[plan['right']]):
                    return 'local_or'
            except (OSError,UnicodeError,csv.Error,ValueError):
                pass
    return local_join_route(workspace,instruction)


async def solve_join_or_task(ctx,bridge):
    if join_or_route(ctx.workspace_dir,ctx.instruction)!='local_or':
        return await solve_local_join_task(ctx,bridge)
    try:
        answer=execute_join_or_plan(parse_join_or_scope(ctx.instruction),select_csv_inputs(ctx.workspace_dir,ctx.instruction))
    except (OSError,UnicodeError,csv.Error,ValueError,TypeError,KeyError,OverflowError) as error:
        return SolveResult(task_id=ctx.task_id,status='UNKNOWN',model_used='',notes='Local OR join rejected: '+type(error).__name__)
    return SolveResult(task_id=ctx.task_id,status='SOLVED',answer=answer,model_used='',notes='Executed full typed equality OR unmatched with all-pairs multiplicity')
