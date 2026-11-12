"""Проверка согласования stdout и answer.txt в data_solver."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import tempfile
import unittest

from harness.config import TaskContext
from harness.agents.data_solver import solve_data_task


class _MockBridge:
    def __init__(self, code: str):
        self.code = code

    async def complete(self, **kwargs):
        return self.code, 100, 20, 0


class DataOutputContractTests(unittest.TestCase):
    def _run_case(self, code: str):
        async def _inner():
            with tempfile.TemporaryDirectory() as tmp:
                tdir = Path(tmp) / "task"
                wdir = tdir / "workspace"
                wdir.mkdir(parents=True)
                (wdir / "custom.csv").write_text("item,qty\na,10\nb,25\n", encoding="utf-8")
                ctx = TaskContext(
                    task_id="data_test",
                    task_type="data_analysis",
                    instruction="Sum qty in custom.csv and write answer.txt.",
                    reward=3,
                    task_dir=tdir,
                    workspace_dir=wdir,
                    max_token_budget=500,
                    allow_reasoning_escalation=False,
                )
                return await solve_data_task(ctx, _MockBridge(code))

        return asyncio.run(_inner())

    def test_file_only_output_is_accepted(self):
        code = "open('answer.txt', 'w').write('35\\n')"
        res = self._run_case(code)
        self.assertEqual(res.status, "SOLVED")
        self.assertEqual(res.answer, "35")

    def test_stdout_only_output_is_accepted(self):
        code = "print(35)"
        res = self._run_case(code)
        self.assertEqual(res.status, "SOLVED")
        self.assertEqual(res.answer, "35")

    def test_conflicting_file_and_stdout_fails(self):
        code = "open('answer.txt', 'w').write('35\\n')\nprint(99)"
        res = self._run_case(code)
        self.assertEqual(res.status, "FAILED")


if __name__ == "__main__":
    unittest.main()