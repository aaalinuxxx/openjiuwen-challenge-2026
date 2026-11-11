"""Улучшенный солвер для задач исправления багов в коде (coding) с защитой от регрессий."""
import ast
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Dict

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model, select_fallback_model


def _parse_failures_count(output: str) -> int:
    """Извлекает суммарное число упавших тестов (failures + errors) из вывода unittest."""
    m_fail = re.search(r"failures=(\d+)", output)
    m_err = re.search(r"errors=(\d+)", output)
    failed = (int(m_fail.group(1)) if m_fail else 0) + (int(m_err.group(1)) if m_err else 0)
    if failed == 0 and ("FAILED" in output or "Traceback" in output):
        failed = 1
    return failed


def _run_tests(workdir: Path, test_filename: str) -> Tuple[bool, str, int]:
    try:
        proc = subprocess.run(
            [sys.executable, "-B", test_filename],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=8,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        passed = (proc.returncode == 0)
        failed_count = 0 if passed else max(1, _parse_failures_count(output))
        return passed, output.strip(), failed_count
    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired", 999
    except Exception as exc:
        return False, str(exc), 999


def _run_all_tests(workdir: Path, test_sources: Dict[str, bytes]) -> Tuple[bool, str, int]:
    outputs = []
    all_passed = True
    total_failures = 0

    for filename, source in test_sources.items():
        path = workdir / filename
        if not path.exists() or path.read_bytes() != source:
            return False, f"Test modification detected: {filename}", 999
        passed, output, failures = _run_tests(workdir, filename)
        all_passed = all_passed and passed
        total_failures += failures
        outputs.append(f"### {filename}\n{output}")

    # Защитная проверка неизменности тестовых файлов
    if any(not (workdir / name).exists() or (workdir / name).read_bytes() != source
           for name, source in test_sources.items()):
        return False, "Test modification detected during execution", 999

    return all_passed, "\n".join(outputs), total_failures


async def solve_coding_task(ctx: TaskContext, bridge) -> SolveResult:
    test_files = sorted(ctx.workspace_dir.glob("test_*.py"))
    code_files = [
        p for p in sorted(ctx.workspace_dir.glob("*.py"))
        if not p.name.startswith("test_")
    ]
    if not test_files or not code_files:
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Missing code or test file")

    # Honor an explicit repair target; filename ordering is not task intent.
    requested = re.findall(
        r'\b(?:fix|repair|correct|update)\s+(?:the\s+)?(?:bugs?\s+in\s+)?`?([A-Za-z_][A-Za-z0-9_]*\.py)\b',
        ctx.instruction, re.IGNORECASE)
    matches = [p for p in code_files if p.name in requested]
    target_file = matches[0] if len(matches) == 1 else (code_files[0] if len(code_files) == 1 and not requested else None)

    with tempfile.TemporaryDirectory(prefix="oj-coding-") as temp_dir:
        sandbox_dir = Path(temp_dir) / "workspace"
        shutil.copytree(ctx.workspace_dir, sandbox_dir,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        return await _repair(ctx, bridge, sandbox_dir, test_files, target_file)


async def _repair(ctx: TaskContext, bridge, sandbox_dir: Path, test_files, target_file: Path):
    test_sources = {p.name: p.read_bytes() for p in test_files}
    passed, test_out, initial_failures = _run_all_tests(sandbox_dir, test_sources)
    if passed:
        return SolveResult(task_id=ctx.task_id, status="SOLVED", answer="DONE", notes="Tests already pass")

    if target_file is None:
        return SolveResult(task_id=ctx.task_id, status="UNKNOWN", notes="Multiple code modules without an unambiguous repair target")

    original_code = target_file.read_text(encoding="utf-8", errors="replace")
    best_code = original_code
    min_failures = initial_failures
    current_code = original_code
    best_test_out = test_out
    retry_feedback = ""

    test_code = '\n\n'.join(f"### {p.name}\n{p.read_text(encoding='utf-8', errors='replace')}"
                            for p in test_files)

    dependencies = '\n\n'.join(
        f"### Read-only module: {p.name}\n{p.read_text(encoding='utf-8', errors='replace')}"
        for p in sorted(ctx.workspace_dir.glob('*.py'))
        if p != target_file and not p.name.startswith('test_'))

    total_in, total_out, total_r = 0, 0, 0
    models_to_try = [select_primary_model(ctx)]
    fb = select_fallback_model(ctx)
    if fb and fb not in models_to_try:
        models_to_try.append(fb)

    sys_prompt = (
        "Return complete corrected Python code only, without comments or Markdown. "
        "Preserve signatures and satisfy the task constraints and all tests. Never modify tests. "
        "Use UNSOLVABLE only for provably contradictory requirements. "
        "The harness runs tests and writes DONE; do not perform these delivery steps in the returned code."
    )

    for attempt, model in enumerate(models_to_try, 1):
        user_prompt = (
            f"### Task constraints\n{ctx.instruction}\n\n"
            f"### Target File: {target_file.name}\n{current_code}\n\n"
            f"{dependencies}\n\n{test_code}\n\n"
            f"### Failing Test Output (failures: {min_failures})\n{test_out}\n{retry_feedback}"
        )
        resp, in_tok, out_tok, r_tok = await bridge.complete(
            model=model, system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=700
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

        # Очищаем markdown-разметку, если модель добавила её
        patched_code = re.sub(r"^```(?:python)?|```$", "", resp.strip(), flags=re.MULTILINE).strip()

        # Быстрая валидация синтаксиса в памяти
        try:
            ast.parse(patched_code)
        except SyntaxError as exc:
            retry_feedback = f"Previous candidate was invalid Python ({exc.msg}, line {exc.lineno}); it was discarded."
            continue

        (sandbox_dir / target_file.name).write_text(patched_code + "\n", encoding="utf-8")
        passed_now, new_test_out, new_failures = _run_all_tests(sandbox_dir, test_sources)

        if passed_now:
            # Успех: копируем рабочий патч обратно в рабочий каталог задачи
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

        # Continue from the best candidate with its matching traceback.
        if new_failures <= min_failures:
            min_failures = new_failures
            best_code = patched_code
            best_test_out = new_test_out
            retry_feedback = ""
        else:
            retry_feedback = f"Previous candidate increased failures to {new_failures}; it was discarded."
        current_code = best_code
        test_out = best_test_out
        (sandbox_dir / target_file.name).write_text(best_code + "\n", encoding="utf-8")

    return SolveResult(
        task_id=ctx.task_id,
        status="FAILED",
        input_tokens=total_in,
        output_tokens=total_out,
        reasoning_tokens=total_r,
        model_used=models_to_try[-1],
        notes=f"Tests still failing after patch attempts (min failures: {min_failures})",
    )