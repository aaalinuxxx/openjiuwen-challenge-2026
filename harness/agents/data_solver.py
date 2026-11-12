"""Ультра-экономный солвер для задач анализа данных (data_analysis)."""
import csv
import re
from pathlib import Path

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model
from harness.sandbox.executor import run_csv_snippet
from harness.agents.calculation_plans import parse_sales_plan, execute_sales_plan
from harness.agents.instruction_scope import sales_source_name


def _try_fast_sales_pattern(csv_path: Path, instruction: str) -> str | None:
    """
    Решает типовой шаблон:
    "How many units of product 'widget' were sold in months 5 through 6 inclusive?"
    за 0 токенов напрямую на Python.
    """
    plan = parse_sales_plan(instruction)
    if plan is None:
        return None
    status, answer = execute_sales_plan(csv_path, plan)
    return answer if status == "SOLVED" else status



async def solve_data_task(ctx: TaskContext, bridge) -> SolveResult:
    csv_files = sorted(ctx.workspace_dir.glob("*.csv"))
    if not csv_files:
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Нет CSV файла")

    source_name = sales_source_name(ctx.instruction)
    if source_name is not None:
        matches = [p for p in csv_files if p.name.casefold() == source_name.casefold()]
        if not matches:
            return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Named CSV is missing")
        if len(matches) != 1:
            return SolveResult(task_id=ctx.task_id, status="UNKNOWN", notes="Ambiguous named CSV")
        csv_file = matches[0]
    elif len(csv_files) == 1:
        csv_file = csv_files[0]
    else:
        return SolveResult(task_id=ctx.task_id, status="UNKNOWN", notes="Multiple CSV files without a recognized instruction")

    fast = _try_fast_sales_pattern(csv_file, ctx.instruction)
    if fast == "UNSOLVABLE":
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Нет нужных колонок в CSV")
    if fast == "UNKNOWN":
        return SolveResult(task_id=ctx.task_id, status="UNKNOWN", notes="Неоднозначные данные или правило округления")
    if fast is not None:
        return SolveResult(
            task_id=ctx.task_id,
            status="SOLVED",
            answer=fast,
            notes="Solved zero-token via CSV parser",
        )

    # Для произвольного аналитического запроса подаём в LLM только первые 4 строки CSV
    sample_lines = csv_file.read_text(encoding="utf-8", errors="replace").splitlines()[:4]
    model = select_primary_model(ctx)
    sys_prompt = (
        "Write ONLY raw executable Python 3 code (no markdown fences, no explanations) "
        "that reads the CSV file in the current directory and prints ONLY the final answer to stdout. "
        "The harness handles any instruction to write answer.txt; your program must only print the result. Use the standard library. Read all rows; the preview is incomplete. Do not modify input files."
    )
    user_prompt = (
        f"File: {csv_file.name}\n"
        f"Header & first rows:\n" + "\n".join(sample_lines) + "\n\n"
        f"Task: {ctx.instruction}"
    )

    code_resp, in_tok, out_tok, r_tok = await bridge.complete(
        model=model, system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=200
    )
    clean_code = re.sub(r"^```(?:python)?\s*|```$", "", code_resp.strip(), flags=re.MULTILINE).strip()

    status, answer, note = run_csv_snippet(clean_code, [csv_file])
    return SolveResult(
        task_id=ctx.task_id, status=status, answer=answer,
        input_tokens=in_tok, output_tokens=out_tok, reasoning_tokens=r_tok,
        model_used=model, notes=note,
    )
