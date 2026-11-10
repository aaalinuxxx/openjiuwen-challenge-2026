"""Статическое извлечение признаков задачи за 0 токенов."""
import ast
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

from harness.config import TaskFeatures


def inspect_coding_tests(workspace_dir: Path) -> Tuple[int, int, bool, bool]:
    """Запускает тесты за 0 токенов и проверяет AST на взаимоисключающие assertEqual."""
    test_files = sorted(workspace_dir.glob("test_*.py"))
    if not test_files:
        return 0, 0, False, False

    test_file = test_files[0]
    has_syntax_error = False
    conflicting_asserts = False

    try:
        source = test_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
        # Простая детекция прямых противоречий вида self.assertEqual(f(x), y1) и self.assertEqual(f(x), y2)
        seen_calls: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "assertEqual" and len(node.args) >= 2:
                    call_repr = ast.unparse(node.args[0])
                    val_repr = ast.unparse(node.args[1])
                    if call_repr in seen_calls and seen_calls[call_repr] != val_repr:
                        conflicting_asserts = True
                    seen_calls[call_repr] = val_repr
    except SyntaxError:
        has_syntax_error = True
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [sys.executable, test_file.name],
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        stderr = proc.stderr or ""
        m_ran = re.search(r"Ran\s+(\d+)\s+test", stderr)
        total = int(m_ran.group(1)) if m_ran else 0
        m_fail = re.search(r"failures=(\d+)", stderr)
        m_err = re.search(r"errors=(\d+)", stderr)
        failed = (int(m_fail.group(1)) if m_fail else 0) + (int(m_err.group(1)) if m_err else 0)
        if proc.returncode != 0 and failed == 0:
            failed = 1
        return total, failed, has_syntax_error, conflicting_asserts
    except subprocess.TimeoutExpired:
        # A timeout can be a repairable loop, not a contradictory specification.
        return 1, 1, has_syntax_error, conflicting_asserts
    except Exception:
        return 0, 1, has_syntax_error, conflicting_asserts


def extract_task_features(task_dir: Path) -> Tuple[Dict[str, Any], TaskFeatures]:
    """Читает task.json и собирает быстрые признаки задачи без вызова LLM."""
    task_json_path = task_dir / "task.json"
    meta = json.loads(task_json_path.read_text(encoding="utf-8"))

    task_id = str(meta.get("task_id", task_dir.name))
    instruction = str(meta.get("instruction", ""))
    reward = int(meta.get("reward", 1))

    # Если task_type скрыт, определяем по сигнатурам инструкции и файлов
    task_type = str(meta.get("task_type", "")).strip().lower()
    workspace_dir = task_dir / "workspace"
    if not workspace_dir.exists():
        workspace_dir = task_dir

    all_files = [p for p in workspace_dir.rglob("*") if p.is_file() and p.name != "task.json"]
    total_bytes = sum(p.stat().st_size for p in all_files)

    if not task_type:
        if any(p.name.startswith("test_") and p.suffix == ".py" for p in all_files):
            task_type = "coding"
        elif any(p.suffix == ".csv" for p in all_files):
            task_type = "data_analysis"
        elif (workspace_dir / "kb").exists():
            task_type = "search"
        else:
            task_type = "math"

    csv_rows = 0
    kb_files_count = 0
    initial_tests_total = 0
    initial_tests_failed = 0
    has_syntax_error = False
    missing_entity_or_column = False
    conflicting_tests = False

    if task_type == "data_analysis":
        csv_files = list(workspace_dir.glob("*.csv"))
        if not csv_files:
            missing_entity_or_column = True
        else:
            try:
                with csv_files[0].open("r", encoding="utf-8", errors="replace") as f:
                    reader = list(csv.reader(f))
                    csv_rows = max(0, len(reader) - 1)
                    # A header-only table is valid for sum/count (answer may be 0).
                    # Required schema is checked by the domain solver.
            except Exception:
                missing_entity_or_column = True

    elif task_type == "search":
        kb_dir = workspace_dir / "kb"
        if not kb_dir.exists():
            missing_entity_or_column = True
        else:
            md_files = list(kb_dir.glob("*.md"))
            kb_files_count = len(md_files)
            if kb_files_count == 0:
                missing_entity_or_column = True
            else:
                kb_corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in md_files)
                # Capitalization alone does not identify a requested entity.
                # Resolve entities and required links in the search solver.

    elif task_type == "coding":
        initial_tests_total, initial_tests_failed, has_syntax_error, conflicting_tests = inspect_coding_tests(workspace_dir)

    features = TaskFeatures(
        task_id=task_id,
        task_type=task_type,
        reward=reward,
        instruction_len=len(instruction),
        num_files=len(all_files),
        total_bytes=total_bytes,
        csv_rows=csv_rows,
        kb_files_count=kb_files_count,
        initial_tests_total=initial_tests_total,
        initial_tests_failed=initial_tests_failed,
        has_syntax_error=has_syntax_error,
        missing_entity_or_column=missing_entity_or_column,
        conflicting_tests_detected=conflicting_tests,
    )
    return meta, features
