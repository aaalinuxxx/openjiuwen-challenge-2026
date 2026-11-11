"""Experimental typed join plans; no generated Python or SQL is executed."""
import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
import re

from harness.config import SolveResult
from harness.agents.calculation_plans import decimal_text
from harness.agents.model_router import select_primary_model
from harness.agents.multi_csv import describe_csv, select_csv_inputs

SCHEMA = (
    '{"left":"file.csv","right":"other.csv","left_key":"column","right_key":"column",'
    '"join":"inner|left|anti","filter":null,'
    '"aggregate":{"op":"sum|count","side":"left|right|null","column":"name|null"}}. '
    'filter is null or {"side":"left|right","column":"name","equals":"literal string"}. '
    'For count, side and column must be JSON null. For sum both must be strings.'
)

def parse_join_plan(text):
    if text.strip() == "UNSUPPORTED":
        return None
    fenced = re.fullmatch(r"\x60\x60\x60(?:json)?\s*([\s\S]*?)\s*\x60\x60\x60", text.strip())
    if fenced:
        text = fenced.group(1)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)

def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Unexpected plan fields")

def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = reader.fieldnames
        if not columns or any(not c for c in columns) or len(columns) != len(set(columns)):
            raise ValueError("Ambiguous header")
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed row")
            rows.append(row)
        return columns, rows

def execute_join_plan(plan, selected, max_pairs=1000000):
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
        _keys(filt, ("side","column","equals"))
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
                if row is None or row[filt["column"]] != filt["equals"]:
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

async def solve_join_plan_task(ctx, bridge):
    selected = select_csv_inputs(ctx.workspace_dir, ctx.instruction)
    if selected is None:
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Need two explicitly named CSV inputs")
    try:
        description = json.dumps([describe_csv(p) for p in selected],ensure_ascii=False)
    except (OSError, UnicodeError, csv.Error, ValueError):
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Ambiguous CSV input")
    if len(description.encode("utf-8")) > 6000:
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Preview limit exceeded")
    system = (
        "Return ONLY a JSON join plan or the exact word UNSUPPORTED. No Python or SQL. "
        "Schema: " + SCHEMA +
        " The local executor joins exact nonempty string keys, preserving ALL matching pairs, including duplicate rows. "
        "left includes unmatched left rows; absent right sum values contribute zero. anti keeps unmatched left rows. "
        "The optional equality filter applies AFTER the join. Sum is exact decimal arithmetic; count counts result rows. "
        "Only one key per table and at most one string equality filter are supported. "
        "Use UNSUPPORTED for numeric comparisons, rounding, multiple filters, distinct, mean, median, "
        "composite or numeric keys, or any condition not expressible in this schema. Never drop conditions. "
        "Use exact listed filenames and column names. Samples are incomplete; executor reads all rows."
    )
    prompt = "CSV schemas and first three data rows:\n"+description+"\nTask: "+ctx.instruction
    model = select_primary_model(ctx)
    response, inp, out, reasoning = await bridge.complete(
        model=model,system_prompt=system,user_prompt=prompt,max_tokens=400)
    counts = dict(input_tokens=inp,output_tokens=out,reasoning_tokens=reasoning,model_used=model)
    try:
        plan = parse_join_plan(response)
        if plan is None:
            return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Model declared unsupported conditions",**counts)
        answer = execute_join_plan(plan,selected)
    except (OSError, UnicodeError, csv.Error, ValueError, TypeError, KeyError, OverflowError) as error:
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Invalid join plan: "+type(error).__name__,**counts)
    return SolveResult(task_id=ctx.task_id,status="SOLVED",answer=answer,notes="Executed typed join plan; question semantics are not formally verified",**counts)
