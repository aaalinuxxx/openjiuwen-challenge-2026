"""Солвер для задач исправления багов в коде (coding) с верификацией unittest."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model, select_fallback_model


def _run_tests(workdir: Path, test_filename: str) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-B", test_filename],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=8,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return proc.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired"


def _run_all_tests(workdir: Path, test_sources):
    outputs = []
    all_passed = True
    for filename, source in test_sources.items():
        path = workdir / filename
        if not path.exists() or path.read_bytes() != source:
            return False, f"Test modification detected: {filename}"
        passed, output = _run_tests(workdir, filename)
        all_passed = all_passed and passed
        outputs.append(f"### {filename}\n{output}")
    if any(not (workdir / name).exists() or (workdir / name).read_bytes() != source
           for name, source in test_sources.items()):
        return False, "Test modification detected during execution"
    return all_passed, "\n".join(outputs)


async def solve_coding_task(ctx: TaskContext, bridge) -> SolveResult:
    test_files = sorted(ctx.workspace_dir.glob("test_*.py"))
    code_files = [
        p for p in sorted(ctx.workspace_dir.glob("*.py"))
        if not p.name.startswith("test_")
    ]
    if not test_files or not code_files:
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Missing code or test file")

    target_file = code_files[0]

    # Unique working copy; cleanup on return, including errors.
    with tempfile.TemporaryDirectory(prefix="oj-coding-") as temp_dir:
        sandbox_dir = Path(temp_dir) / "workspace"
        shutil.copytree(ctx.workspace_dir, sandbox_dir,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        return await _repair(ctx, bridge, sandbox_dir, test_files, target_file)


async def _repair(ctx, bridge, sandbox_dir, test_files, target_file):

    test_sources = {p.name: p.read_bytes() for p in test_files}
    passed, test_out = _run_all_tests(sandbox_dir, test_sources)
    if passed:
        return SolveResult(task_id=ctx.task_id, status="SOLVED", answer="DONE", notes="Tests already pass")

    src_code = target_file.read_text(encoding="utf-8", errors="replace")
    test_code = '\n\n'.join(f"### {p.name}\n{p.read_text(encoding='utf-8', errors='replace')}"
                              for p in test_files)

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
            f"{test_code}\n\n"
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

        passed_now, test_out = _run_all_tests(sandbox_dir, test_sources)
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

        # Next traceback was produced by this patch, not the original module.
        src_code = patched_code

    return SolveResult(
        task_id=ctx.task_id,
        status="FAILED",
        input_tokens=total_in,
        output_tokens=total_out,
        reasoning_tokens=total_r,
        model_used=models_to_try[-1],
        notes="Tests still failing after patch attempts",
    )
