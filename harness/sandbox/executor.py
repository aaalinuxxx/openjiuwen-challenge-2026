"""Изолированный запуск однострочников и скриптов Python с жёстким таймаутом."""
import subprocess
import sys
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

def _extract_execution_answer(stdout: str, cwd: Path, ok: bool, error: str) -> str | None:
    """Вспомогательная функция: вытаскивает ответ из stdout или из файла answer.txt."""
    if not ok:
        return None

    # 1. Пробуем взять из файла answer.txt (если он есть)
    answer_file = cwd / "answer.txt"
    if answer_file.is_file():
        try:
            content = answer_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    # 2. Если файла нет, берем из stdout (ровно одну строчку)
    lines = stdout.strip().splitlines()
    if len(lines) == 1 and lines[0].strip():
        return lines[0].strip()

    return None