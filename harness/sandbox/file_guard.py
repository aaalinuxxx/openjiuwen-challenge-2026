"""Атомарное сохранение answer.txt и сводного файла $OUT после каждой решённой задачи."""
import json
import os
from pathlib import Path
from typing import Optional


def _atomic_write_text(target: Path, content: str) -> None:
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)


def save_task_answer(
    task_dir: Path,
    workspace_dir: Path,
    task_id: str,
    answer: str,
    global_out_path: Optional[Path] = None,
) -> None:
    clean_answer = str(answer).strip() + "\n"

    # Записываем и в корень задачи (/data/tasks/<task_id>/answer.txt),
    # и в workspace/answer.txt (если подкаталог workspace существует)
    _atomic_write_text(task_dir / "answer.txt", clean_answer)
    if workspace_dir != task_dir and workspace_dir.exists():
        _atomic_write_text(workspace_dir / "answer.txt", clean_answer)

    # Если проверяющая система передала переменную окружения OUT
    if global_out_path is not None:
        try:
            if global_out_path.is_dir():
                out_file = global_out_path / "solutions.json"
            else:
                out_file = global_out_path
            existing = {}
            if out_file.exists():
                try:
                    existing = json.loads(out_file.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            existing[task_id] = str(answer).strip()
            _atomic_write_text(out_file, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
        except Exception:
            pass
