"""Regression controls for bounded KB context and request deadline accounting."""
import asyncio
from pathlib import Path
import tempfile
import unittest

from harness.agents.kb_context import build_kb_context
from harness.agents.search_solver import _parse_kb, _resolve_graph_query, solve_search_task
from harness.agents.base_harness import solve_task
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker


class KBContextTests(unittest.TestCase):
    def test_depth_limit_and_cycle(self):
        kb = {'A': {'mentor': 'B'}, 'B': {'mentor': 'C'}, 'C': {'mentor': 'A'}}
        limited = build_kb_context('About A', kb, max_hops=1)
        self.assertEqual(limited.names, ('A', 'B'))
        self.assertIn('depth_limit', limited.limits)
        self.assertFalse(limited.complete_kb)
        whole = build_kb_context('About A', kb, max_hops=2)
        self.assertEqual(whole.names, ('A', 'B', 'C'))
        self.assertTrue(whole.complete_kb)

    def test_order_independent_and_whole_name_roots(self):
        kb = {'Ann': {'born': '9999'}, 'Anne': {'mentor': 'B'}, 'B': {'born': '1990'}}
        left = build_kb_context('About ANNE', kb)
        right = build_kb_context('About ANNE', dict(reversed(list(kb.items()))))
        self.assertEqual(left, right)
        self.assertEqual(left.names, ('Anne', 'B'))
        self.assertNotIn('9999', left.text)

    def test_unicode_bytes_and_whole_records(self):
        kb = {'Анна': {'born': '1990'}, 'Борис': {'born': '1980'}}
        one = build_kb_context('Анна', kb)
        byte_cap = len(one.text.encode('utf-8'))
        bounded = build_kb_context('без имени', kb, max_bytes=byte_cap)
        self.assertEqual(bounded.names, ('Анна',))
        self.assertEqual(bounded.text, one.text)
        self.assertIn('byte_limit', bounded.limits)
        too_small = build_kb_context('Анна', kb, max_bytes=byte_cap-1)
        self.assertEqual(too_small.text, '')
        self.assertEqual(too_small.names, ())

    def test_all_conflicting_links_and_sources_preserved(self):
        kb = {
            'A': {'employer': 'B', '_conflicts': {'employer': {'B': ['x.md'], 'c': ['y.md']}}},
            'B': {'headquarters': 'Lima'}, 'C': {'headquarters': 'Oslo'},
        }
        result = build_kb_context('About A', kb)
        self.assertEqual(result.names, ('A', 'B', 'C'))
        self.assertTrue(result.complete_kb)
        for value in ('CONFLICT', 'Lima', 'Oslo', 'x.md', 'y.md'):
            self.assertIn(value, result.text)

    def test_invalid_bounds_rejected(self):
        for kwargs in ({'max_hops': -1}, {'max_records': 0}, {'max_bytes': 0},
                       {'max_hops': True}, {'max_records': 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_kb_context('A', {}, **kwargs)

    def test_conflicts_only_block_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb/'a.md').write_text('# Ada\nBorn: 1990\nEmployer: Orbit\n', encoding='utf-8')
            (kb/'b.md').write_text('# Ada\nBorn: 1991\nEmployer: Orbit\n', encoding='utf-8')
            (kb/'c.md').write_text('# Orbit\nHeadquarters: Lima\n', encoding='utf-8')
            entities = _parse_kb(kb)
            self.assertEqual(_resolve_graph_query("In which city is the headquarters of Ada's employer?", entities)[:2],
                             ('SOLVED', 'Lima'))
            self.assertEqual(_resolve_graph_query('In which year was Ada born?', entities)[0], 'UNKNOWN')


class SearchRefusalTests(unittest.IsolatedAsyncioTestCase):
    async def test_refusal_requires_complete_kb(self):
        class Bridge:
            reply = 'UNSOLVABLE'
            async def complete(self, **kwargs):
                return self.reply, 20, 2, 0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'kb').mkdir()
            (root/'kb'/'a.md').write_text('# Ada\nBorn: 1990\n', encoding='utf-8')
            ctx = TaskContext('test', 'search', 'Tell me the birthday of Ada.', 1, root, root, 1000, False)
            bridge = Bridge()
            result = await solve_search_task(ctx, bridge)
            self.assertEqual(result.status, 'UNSOLVABLE')
            (root/'kb'/'b.md').write_text('# Other\nBorn: 1980\n', encoding='utf-8')
            result = await solve_search_task(ctx, bridge)
            self.assertEqual(result.status, 'UNKNOWN')
            self.assertIsNone(result.answer)
            self.assertEqual(result.input_tokens, 20)
            bridge.reply = 'UNKNOWN'
            (root/'kb'/'b.md').unlink()
            self.assertEqual((await solve_search_task(ctx, bridge)).status, 'UNKNOWN')

    async def test_oversized_only_card_never_calls_model(self):
        class ForbiddenBridge:
            async def complete(self, **kwargs):
                raise AssertionError('Oversized record must not trigger a request')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'kb').mkdir()
            (root/'kb'/'a.md').write_text('# Ada\nBiography: '+('я'*12000), encoding='utf-8')
            ctx = TaskContext('test', 'search', 'Tell me about Ada.', 1, root, root, 1000, False)
            self.assertEqual((await solve_search_task(ctx, ForbiddenBridge())).status, 'UNKNOWN')


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_and_misordered_timeouts(self):
        for value in (0, -1, True, float('nan'), float('inf'), '60'):
            for field in ('request_timeout_sec', 'workflow_timeout_sec'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    HarnessConfig(Path('.'), None, 'https://fixture.invalid', '', **{field: value})
        with self.assertRaises(ValueError):
            HarnessConfig(Path('.'), None, 'https://fixture.invalid', '', request_timeout_sec=2, workflow_timeout_sec=2)

    async def test_timeout_stops_new_requests_but_keeps_local_work(self):
        calls = 0
        cancelled = asyncio.Event()
        async def stalled(payload):
            nonlocal calls
            calls += 1
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        config = HarnessConfig(Path('.'), None, 'https://fixture.invalid', '', request_timeout_sec=0.02, workflow_timeout_sec=1)
        tracker = BudgetTracker(1000)
        ctx = TaskContext('first', 'other', 'Say OK.', 1, Path('.'), Path('.'), 1000, False)
        result = await solve_task(ctx, config, tracker, stalled)
        self.assertEqual(result.status, 'ACCOUNTING_UNKNOWN')
        self.assertTrue(cancelled.is_set())
        self.assertTrue(tracker.has_unaccounted_request)
        self.assertGreater(tracker.reserved_effective_tokens, 0)
        self.assertEqual(tracker.spent_effective_tokens, 0)
        ctx.task_id = 'second'
        self.assertEqual((await solve_task(ctx, config, tracker, stalled)).status, 'BUDGET_EXCEEDED')
        self.assertEqual(calls, 1)
        ctx.task_type = 'math'
        ctx.instruction = 'A warehouse starts with 10 boxes. It receives 2 boxes. How many boxes does it have at the end?'
        result = await solve_task(ctx, config, tracker, stalled)
        self.assertEqual((result.status, result.answer), ('SOLVED', '12'))
        self.assertEqual(calls, 1)


if __name__ == '__main__':
    unittest.main()
