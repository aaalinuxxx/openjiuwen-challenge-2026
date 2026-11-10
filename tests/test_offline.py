import contextlib
import io
import os
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.agents.math_solver import _try_warehouse_math_zero_token
from run_agent import parse_args


class LocalRegressionTests(unittest.TestCase):
    def test_budget_precedence(self):
        with patch.dict(os.environ, {'BUDGET': '100', 'TOKEN_BUDGET': '200'}):
            self.assertEqual(parse_args([]).budget, 100)
            self.assertEqual(parse_args(['--budget', '50']).budget, 50)

    def test_default_and_legacy_budget(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(parse_args([]).budget, 100000)
            os.environ['TOKEN_BUDGET'] = '125'
            self.assertEqual(parse_args([]).budget, 125)

    def test_invalid_budget(self):
        for value in ('-1', 'nan', 'inf', 'wrong'):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parse_args(['--budget', value])

    def test_filename_does_not_force_api(self):
        rng = random.Random(731)
        for _ in range(100):
            initial = rng.randint(1000, 10000)
            daily, days, shipments, amount = [rng.randint(1, 10) for _ in range(4)]
            text = (f'A warehouse starts with {initial} boxes. '
                    f'It ships {daily} boxes per day for {days} days. '
                    f'It receives {shipments} deliveries of {amount} boxes each. '
                    'How many boxes does it have at the end? Compute it with Python. '
                    'Work only inside the current directory. '
                    'When you are done, write ONLY the final answer to answer.txt in the current directory.')
            self.assertEqual(_try_warehouse_math_zero_token(text),
                             str(initial - daily*days + shipments*amount))

    def test_rounding_each_step(self):
        text = ('A warehouse starts with 17 boxes. Then the stock is split equally into 3 '
                'warehouses and it keeps one share (rounded down). Then the stock is doubled '
                'by merging with a sister warehouse. How many boxes does it have at the end?')
        self.assertEqual(_try_warehouse_math_zero_token(text), '10')

    def test_unknown_operation_requires_fallback(self):
        text = ('A warehouse starts with 100 boxes. Then 20 boxes are destroyed. '
                'How many boxes does it have at the end?')
        self.assertIsNone(_try_warehouse_math_zero_token(text))


if __name__ == '__main__':
    unittest.main()
