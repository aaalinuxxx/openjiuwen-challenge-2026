import asyncio
import contextlib
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from generate_dataset1 import generate_pool
from main_offline_benchmark import parse_args
from harness.config import TaskContext
from harness.agents.coding_solver import solve_coding_task
from harness.agents.calculation_plans import parse_sales_plan


class DatasetAndModeTests(unittest.TestCase):
    def test_generator_seed_and_impossible_math(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            outputs = []
            for n in range(2):
                random.seed(n + 101)
                root = Path(tmp)/str(n)
                generate_pool(root, total=41, seed=42)
                outputs.append({p.relative_to(root).as_posix():p.read_bytes()
                                for p in root.rglob('*') if p.is_file()})
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(sum(p.endswith('task.json') for p in outputs[0]), 41)
            for path, raw in outputs[0].items():
                if not path.endswith('task.json'):
                    continue
                task = json.loads(raw)
                if task['task_type'] == 'math':
                    self.assertEqual('split equally into 0 warehouses' in task['instruction'], task['unsolvable'])
            with self.assertRaises(ValueError):
                generate_pool(Path(tmp)/'0')

    def test_offline_rejects_positive_budget_and_live_requires_budget(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for args in (['--budget', '5000'], ['--budget', '100'], ['--live']):
                with self.assertRaises(SystemExit):
                    parse_args(args)
        self.assertFalse(parse_args([]).live)
        self.assertEqual(parse_args([]).budget, 0)

    def test_known_administrative_sentence_not_arbitrary_constraints(self):
        question = "How many units of product 'widget' were sold in months 1 through 2 inclusive?"
        tail = " When you are done, write ONLY the final answer to the file answer.txt in the current directory."
        self.assertIsNotNone(parse_sales_plan(question+tail))
        self.assertIsNone(parse_sales_plan(question+" Exclude refunds."+tail))


class CodingRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, first):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = 'def f(): return 0\ndef g(): return 1\n'
            (root/'mylib.py').write_text(original)
            (root/'test_a.py').write_text('import unittest\nimport mylib\n'
                'class T(unittest.TestCase):\n'
                '    def test_f(self): self.assertEqual(mylib.f(), 1)\n'
                '    def test_g(self): self.assertEqual(mylib.g(), 1)\n'
                'if __name__=="__main__": unittest.main()\n')
            prompts = []
            replies = [first, 'def f(): return 1\ndef g(): return 1\n']
            class Bridge:
                async def complete(self, **kwargs):
                    prompts.append(kwargs['user_prompt'])
                    return replies.pop(0), 0, 0, 0
            ctx = TaskContext('case', 'coding', 'Fix bugs.', 4, root, root, 2000, True)
            result = await solve_coding_task(ctx, Bridge())
            self.assertEqual(result.status, 'SOLVED')
            self.assertIn('Fix bugs.', prompts[0])
            return prompts, original

    async def test_regression_rolls_back_prompt_and_traceback_together(self):
        prompts, original = await self.run_case('def f(): return 0\ndef g(): return 0\n')
        self.assertIn(original.strip(), prompts[1])
        self.assertIn('failures: 1', prompts[1])
        self.assertIn('FAILED (failures=1)', prompts[1])
        self.assertNotIn('FAILED (failures=2)', prompts[1])
        self.assertIn('increased failures to 2', prompts[1])

    async def test_invalid_syntax_keeps_best_code_and_explains_rejection(self):
        prompts, original = await self.run_case('def f(')
        self.assertIn(original.strip(), prompts[1])
        self.assertIn('invalid Python', prompts[1])

class CodingEvaluationTests(unittest.TestCase):
    def test_done_is_verified_by_tests_not_expected_marker(self):
        from main_offline_benchmark import verify_coding
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test = b"from mylib import f\nassert f() == 2\n"
            (root/'test_a.py').write_bytes(test)
            (root/'mylib.py').write_text('def f(): return 2\n')
            protected = {Path('test_a.py'): test}
            self.assertTrue(verify_coding(root, protected, 'DONE'))
            self.assertFalse(verify_coding(root, protected, None))
            (root/'mylib.py').write_text('def f(): return 1\n')
            self.assertFalse(verify_coding(root, protected, 'DONE'))
            (root/'test_a.py').write_text('pass\n')
            self.assertFalse(verify_coding(root, protected, 'DONE'))

class CodingBudgetTests(unittest.TestCase):
    def test_coding_floor_cannot_exceed_available_global_budget(self):
        from harness.planner.budget_tracker import BudgetTracker
        for budget, expected in [(0, 0), (300, 300), (2000, 800)]:
            tracker = BudgetTracker(budget)
            self.assertEqual(tracker.allocate_task_budget(200, 2, minimum=800), expected)
        self.assertEqual(BudgetTracker(2000).allocate_task_budget(200, 2), 360)
