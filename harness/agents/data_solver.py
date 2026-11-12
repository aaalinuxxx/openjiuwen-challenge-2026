"""Ультра-экономный солвер для задач анализа данных (data_analysis)."""
import csv
import re
from pathlib import Path

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model
from harness.sandbox.executor import run_python_snippet
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


def _extract_execution_answer(stdout: str, answer_file: Path) -> tuple[str | None, str]:
    """
    Согласовывает результат из stdout и/или answer.txt, созданного скриптом модели.
    Возвращает (answer, error_note).
    """
    stdout_lines = [ln.strip() for ln in stdout.strip().splitlines() if ln.strip()]
    stdout_ans = stdout_lines[-1] if stdout_lines else None

    file_ans = None
    if answer_file.exists():
        file_text = answer_file.read_text(encoding="utf-8", errors="replace").strip()
        file_lines = [ln.strip() for ln in file_text.splitlines() if ln.strip()]
        file_ans = file_lines[-1] if file_lines else None
        # Убираем временный answer.txt из workspace, чтобы итоговую запись делал file_guard
        try:
            answer_file.unlink()
        except OSError:
            pass

    if stdout_ans and file_ans and stdout_ans != file_ans:
        return None, f"Conflicting outputs: stdout={stdout_ans!r} vs file={file_ans!r}"

    ans = stdout_ans or file_ans
    if not ans:
        return None, "Empty stdout and no answer.txt produced"
    return ans, ""


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
        "Do NOT write answer.txt yourself; only print the final result."
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

    answer_file = ctx.workspace_dir / "answer.txt"
    if answer_file.exists():
        try:
            answer_file.unlink()
        except OSError:
            pass

    ok, stdout, err = run_python_snippet(clean_code, cwd=ctx.workspace_dir)

    if ok:
        ans, extract_err = _extract_execution_answer(stdout, answer_file)
        if ans is not None:
            return SolveResult(
                task_id=ctx.task_id,
                status="SOLVED",
                answer=ans,
                input_tokens=in_tok,
                output_tokens=out_tok,
                reasoning_tokens=r_tok,
                model_used=model,
            )
        err = extract_err or err

    return SolveResult(
        task_id=ctx.task_id,
        status="FAILED",
        input_tokens=in_tok,
        output_tokens=out_tok,
        reasoning_tokens=r_tok,
        model_used=model,
        notes=err[:200],
    )