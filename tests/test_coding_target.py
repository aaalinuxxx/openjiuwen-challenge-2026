"""Scope controls for repair target selection."""
import json
from pathlib import Path
import tempfile
import unittest
from harness.agents.coding_target import select_coding_target
from harness.agents.coding_solver import solve_coding_task
from harness.config import TaskContext

CONTROLS = json.loads("[[\"Fix z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"The bug is in z_filter.py; change that module only.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Only modify `z_filter.py`. Do not edit a_settings.py.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Target file: z_filter.py. Leave a_settings.py unchanged.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Repair the module z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Please fix the bug in z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Fix bugs.\",[\"z_filter.py\"],\"z_filter.py\"],[\"Do not fix z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Never repair z_filter.py.\",[\"z_filter.py\"],null],[\"Don't edit z_filter.py. Fix z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"The log says \\\"Fix z_filter.py\\\".\",[\"z_filter.py\"],null],[\"Example: 'Repair z_filter.py'.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"```\\nFix z_filter.py.\\n```\",[\"z_filter.py\"],null],[\"Fix missing.py. Fix z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix missing.py.\",[\"z_filter.py\"],null],[\"Fix z_filter.py and a_settings.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix z_filter.py. Repair a_settings.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix z_filter.py. z_filter.py is read-only.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix z_filter.py. Leave z_filter.py unchanged.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Repair both modules.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix ../z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix pkg/z_filter.py.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix test_filter.py.\",[\"z_filter.py\"],null],[\"Fix z_filter.py. Do not edit any files.\",[\"a_settings.py\",\"z_filter.py\"],null],[\"Fix z_filter.py. Use threshold from a_settings.py.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Do not edit.\",[\"z_filter.py\"],null],[\"Do not modify tests. Fix bugs.\",[\"z_filter.py\"],\"z_filter.py\"],[\"Run `python3 test_mylib.py` in the current directory; some tests fail. Fix the bugs in mylib.py (do not edit the tests) until all tests pass. Work only inside the current directory. When you are done, write ONLY the word DONE to the file answer.txt in the current directory (for example with bash: echo 42 > answer.txt).\",[\"mylib.py\"],\"mylib.py\"],[\"Run python3 test_mylib.py. Fix mylib.py without editing tests. average(xs) returns the arithmetic mean, or 0 for an empty list. Functions must be pure and deterministic; do not inspect test names or call order. When done, write ONLY DONE to answer.txt.\",[\"mylib.py\"],\"mylib.py\"],[\"Fix mylib.py: keep values at least the threshold returned by settings.threshold(). Preserve that imported function. Do not edit a_settings.py. Do not change tests. Write DONE to answer.txt only after all tests pass.\",[\"a_settings.py\",\"mylib.py\"],\"mylib.py\"],[\"Fix z_filter.py. Keep input values greater than or equal to threshold() from a_settings.py, in their original order, preserving duplicates. Do not modify a_settings.py or tests.\",[\"a_settings.py\",\"z_filter.py\"],\"z_filter.py\"],[\"Repair z_convert.py. convert(value, source, target) converts a length using the METRES_PER_UNIT mapping from a_units.py: value * METRES_PER_UNIT[source] / METRES_PER_UNIT[target]. Do not modify a_units.py or tests.\",[\"a_units.py\",\"z_convert.py\"],\"z_convert.py\"],[\"Correct z_lookup.py. lookup(mapping, query) returns the value at the first insertion-order key whose normalize(key) equals normalize(query), or None when no key matches. Use normalize from a_normalize.py. Do not modify dependencies or tests.\",[\"a_normalize.py\",\"z_lookup.py\"],\"z_lookup.py\"],[\"Update z_totals.py. total(rows) sums Decimal(str(amount)) * RATES[currency] for each (amount, currency), then rounds the final total to two decimals with ROUND_HALF_UP and returns its fixed-point string. For empty input return '0.00'. Use a_rates.py and never modify dependencies or tests.\",[\"a_rates.py\",\"z_totals.py\"],\"z_totals.py\"]]")

class CodingTargetGrammarTests(unittest.TestCase):
    def test_scope_controls(self):
        for instruction, names, expected in CONTROLS:
            with self.subTest(instruction=instruction):
                result = select_coding_target(instruction, [Path(n) for n in names])
                self.assertEqual(result.name if result else None, expected)

class CodingTargetNoRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_forbidden_target_never_requests_or_changes_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = 'def value(): return 0\n'
            (root/'z_filter.py').write_text(source)
            (root/'test_filter.py').write_text('from z_filter import value\nassert value() == 1\n')
            class Bridge:
                async def complete(self, **kwargs):
                    raise AssertionError('Forbidden repair must not request API')
            result = await solve_coding_task(TaskContext('forbidden','coding','Do not fix z_filter.py.',2,root,root,1200,False),Bridge())
            self.assertEqual(result.status,'UNKNOWN')
            self.assertEqual((root/'z_filter.py').read_text(),source)
