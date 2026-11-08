"""Изолированный запуск однострочников и скриптов Python с жёстким таймаутом."""
import subprocess
from pathlib import Path
from typing import Tuple


def run_python_snippet(code: str, cwd: Path, timeout_sec: int = 8) -> Tuple[bool, str, str]:
    try:
        proc = subprocess.run(
            ["python3", "-c", code],
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
