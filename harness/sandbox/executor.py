"""Изолированный запуск однострочников и скриптов Python с жёстким таймаутом."""
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple


def run_python_snippet(code: str, cwd: Path, timeout_sec: int = 8) -> Tuple[bool, str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return proc.returncode == 0, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return False, "", "TimeoutExpired"
    except Exception as exc:
        return False, "", str(exc)


def extract_execution_answer(stdout: str, answer_file: Path) -> tuple[str | None, str]:
    """Accept one line per present channel; two channels must agree exactly."""
    stdout_answer = stdout.strip()
    if stdout_answer and len(stdout_answer.splitlines()) != 1:
        return None, "Expected exactly one stdout answer line"
    file_answer = None
    if answer_file.is_symlink():
        return None, "Answer file must not be a symbolic link"
    if answer_file.exists():
        if not answer_file.is_file():
            return None, "Answer path is not a regular file"
        try:
            file_answer = answer_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return None, "Answer file is unreadable or not UTF-8"
        if not file_answer or len(file_answer.splitlines()) != 1:
            return None, "Expected exactly one answer.txt line"
    if stdout_answer and file_answer is not None and stdout_answer != file_answer:
        return None, "Conflicting stdout and answer.txt outputs"
    answer = stdout_answer or file_answer
    return (answer, "") if answer else (None, "No answer produced")


def run_csv_snippet(code: str, inputs: list[Path], timeout_sec: int = 8):
    """Execute in disposable CSV copies; only the caller may publish an answer.

    A temporary cwd prevents incidental writes to the task's source files. This
    is not an OS security sandbox for hostile Python or absolute-path accesses.
    """
    originals = {path.name: path.read_bytes() for path in inputs}
    if len(originals) != len(inputs):
        return "UNKNOWN", None, "Ambiguous input filenames"
    with tempfile.TemporaryDirectory(prefix="oj-csv-exec-") as temp:
        root = Path(temp)
        for name, raw in originals.items():
            (root / name).write_bytes(raw)
        ok, stdout, error = run_python_snippet(code, cwd=root, timeout_sec=timeout_sec)
        try:
            unchanged = all(
                not (root / name).is_symlink() and (root / name).is_file()
                and (root / name).read_bytes() == raw
                for name, raw in originals.items()
            )
            unexpected = any(p.name not in originals and p.name != "answer.txt"
                             for p in root.iterdir())
        except OSError:
            return "UNKNOWN", None, "Could not verify execution input integrity"
        if not unchanged or unexpected:
            return "UNKNOWN", None, "Generated code changed inputs or created unexpected files"
        if not ok:
            return "FAILED", None, error[:200] or "Generated program failed"
        answer, note = extract_execution_answer(stdout, root / "answer.txt")
        if answer is None:
            return "FAILED", None, note
        return "SOLVED", answer, ""
