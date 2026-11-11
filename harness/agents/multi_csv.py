"""Experimental multi-CSV fallback. Not enabled in the production dispatcher."""
import csv
import json
from pathlib import Path
import re
import shutil
import tempfile

from harness.config import SolveResult
from harness.agents.data_solver import solve_data_task
from harness.agents.model_router import select_primary_model
from harness.agents.instruction_scope import sales_source_name
from harness.sandbox.executor import run_python_snippet


def select_csv_inputs(workspace, instruction):
    files = sorted(workspace.glob("*.csv"))
    names = set(re.findall(r"(?<![\w./\\-])([A-Za-z0-9_][A-Za-z0-9_.-]*\.csv)\b", instruction, re.I))
    if re.search(r"(?:[/\\]|\.\./)[A-Za-z0-9_.-]+\.csv\b", instruction, re.I):
        return None
    if len(names) != 2:
        return None
    result = []
    for name in sorted(names):
        matches = [p for p in files if p.name.casefold() == name.casefold()]
        if len(matches) != 1:
            return None
        result.append(matches[0])
    return result


def describe_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = reader.fieldnames
        if not columns or any(not c for c in columns) or len(set(columns)) != len(columns):
            raise ValueError("Missing or ambiguous CSV header")
        count, samples = 0, []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed CSV row")
            count += 1
            if len(samples) < 3:
                samples.append(row)
        return dict(file=path.name,columns=columns,rows=count,sample_rows=samples)


async def solve_multi_csv_task(ctx, bridge):
    files = sorted(ctx.workspace_dir.glob("*.csv"))
    named = set(re.findall(r"\b[A-Za-z0-9_][A-Za-z0-9_.-]*\.csv\b", ctx.instruction, re.I))
    if len(files) <= 1 or (len(named) == 1 and sales_source_name(ctx.instruction) is not None):
        return await solve_data_task(ctx, bridge)
    selected = select_csv_inputs(ctx.workspace_dir, ctx.instruction)
    if selected is None:
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Need exactly two existing, explicitly named CSV inputs")
    try:
        description = json.dumps([describe_csv(p) for p in selected],ensure_ascii=False)
    except (OSError, UnicodeError, csv.Error, ValueError):
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="CSV schema could not be read unambiguously")
    if len(description.encode("utf-8")) > 6000:
        return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Multi-CSV preview exceeds experimental limit")
    model = select_primary_model(ctx)
    system = ("Return only executable Python 3 code using the standard library. "
              "Read the named CSV files in the current directory; print only the final answer. "
              "Do not modify files. Samples are incomplete: compute from all rows. "
              "Keep join keys as strings unless the task explicitly requests numeric keys. "
              "Honor the specified join multiplicity, missing-match handling, filters and rounding.")
    prompt = "CSV schemas and first three data rows:\n" + description + "\nTask: " + ctx.instruction
    code, inp, out, reasoning = await bridge.complete(model=model,system_prompt=system,user_prompt=prompt,max_tokens=400)
    code = re.sub(r"^```(?:python)?|```$", "", code.strip(), flags=re.MULTILINE).strip()
    counts = dict(input_tokens=inp,output_tokens=out,reasoning_tokens=reasoning,model_used=model)
    with tempfile.TemporaryDirectory(prefix="oj-csv-join-") as temp:
        root = Path(temp)
        originals = {p.name:p.read_bytes() for p in selected}
        for path in selected:
            shutil.copyfile(path, root/path.name)
        ok, stdout, error = run_python_snippet(code, cwd=root)
        unchanged = all((root/name).is_file() and (root/name).read_bytes()==raw for name,raw in originals.items())
        unexpected = any(p.name not in originals for p in root.iterdir())
        if not unchanged or unexpected:
            return SolveResult(task_id=ctx.task_id,status="UNKNOWN",notes="Generated code changed execution inputs or created files",**counts)
    lines = stdout.strip().splitlines()
    if not ok or len(lines)!=1:
        return SolveResult(task_id=ctx.task_id,status="FAILED",notes=error[:200] or "Expected one answer line",**counts)
    return SolveResult(task_id=ctx.task_id,status="SOLVED",answer=lines[0].strip(),**counts)
