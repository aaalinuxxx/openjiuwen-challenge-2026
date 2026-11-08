"""Солвер для задач исправления багов в коде (coding) с верификацией unittest."""
import re
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model, select_fallback_model


def _run_tests(workdir: Path, test_filename: str) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["python3", test_filename],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=8,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return proc.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired"


async def solve_coding_task(ctx: TaskContext, bridge) -> SolveResult:
    test_files = sorted(ctx.workspace_dir.glob("test_*.py"))
    code_files = [
        p for p in sorted(ctx.workspace_dir.glob("*.py"))
        if not p.name.startswith("test_")
    ]
    if not test_files or not code_files:
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Missing code or test file")

    test_file = test_files[0]
    target_file = code_files[0]

    # Работаем во временной песочнице /tmp/harness_work/<task_id>, чтобы не испортить файлы до прохождения тестов
    sandbox_dir = Path("/tmp/harness_work") / ctx.task_id
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    shutil.copytree(ctx.workspace_dir, sandbox_dir)

    passed, test_out = _run_tests(sandbox_dir, test_file.name)
    if passed:
        return SolveResult(task_id=ctx.task_id, status="SOLVED", answer="DONE", notes="Tests already pass")

    src_code = target_file.read_text(encoding="utf-8", errors="replace")
    test_code = test_file.read_text(encoding="utf-8", errors="replace")

    total_in, total_out, total_r = 0, 0, 0
    models_to_try = [select_primary_model(ctx)]
    fb = select_fallback_model(ctx)
    if fb and fb not in models_to_try:
        models_to_try.append(fb)

    sys_prompt = (
        "Fix all bugs in the target Python module so that all unit tests pass. "
        "If the unit tests are logically contradictory and impossible to satisfy simultaneously, output ONLY the word UNSOLVABLE. "
        "Otherwise output ONLY the complete corrected Python code for the module without markdown fences or explanations."
    )

    for model in models_to_try:
        user_prompt = (
            f"### {target_file.name}\n{src_code}\n\n"
            f"### {test_file.name}\n{test_code}\n\n"
            f"### Failing Test Output\n{test_out}"
        )
        resp, in_tok, out_tok, r_tok = await bridge.complete(
            model=model, system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=600
        )
        total_in += in_tok
        total_out += out_tok
        total_r += r_tok

        if "UNSOLVABLE" in resp.upper() and len(resp.strip()) < 30:
            return SolveResult(
                task_id=ctx.task_id,
                status="UNSOLVABLE",
                input_tokens=total_in,
                output_tokens=total_out,
                reasoning_tokens=total_r,
                model_used=model,
            )

        patched_code = re.sub(r"^```(?:python)?|```$", "", resp.strip(), flags=re.MULTILINE).strip()
        (sandbox_dir / target_file.name).write_text(patched_code + "\n", encoding="utf-8")

        passed_now, test_out = _run_tests(sandbox_dir, test_file.name)
        if passed_now:
            # Копируем проверенный патч обратно в рабочий каталог задачи
            target_file.write_text(patched_code + "\n", encoding="utf-8")
            return SolveResult(
                task_id=ctx.task_id,
                status="SOLVED",
                answer="DONE",
                input_tokens=total_in,
                output_tokens=total_out,
                reasoning_tokens=total_r,
                model_used=model,
            )

    return SolveResult(
        task_id=ctx.task_id,
        status="FAILED",
        input_tokens=total_in,
        output_tokens=total_out,
        reasoning_tokens=total_r,
        model_used=models_to_try[-1],
        notes="Tests still failing after patch attempts",
    )
