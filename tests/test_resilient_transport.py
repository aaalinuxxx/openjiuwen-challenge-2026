"""Ledger-level transport controls: no network, no secret or real billing."""
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from harness.agents.base_harness import OpenJiuwenLLMBridge, APIHTTPError, TruncatedGeneration
from harness.config import HarnessConfig
from harness.planner.budget_tracker import BudgetTracker, BudgetDenied


class TransportLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, first, second=None):
        tracker = BudgetTracker(1000)
        config = HarnessConfig(Path('.'), None, 'https://fixture.invalid/v1', 'fixture-only')
        bridge = OpenJiuwenLLMBridge(config, tracker)
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = [first, second]
        error = None
        with patch('httpx.AsyncClient', return_value=client):
            try:
                await bridge.complete('qwen3.8-27b-noreason', 'Return OK.', '', max_tokens=20)
            except Exception as exc:
                error = exc
        return tracker, client, error

    def response(self, data=None, status=200, text=None):
        return httpx.Response(status, request=httpx.Request('POST', 'https://fixture.invalid'),
                              **({'text': text} if text is not None else {'json': data}))

    async def test_missing_choices_cost_preserved_without_retry(self):
        tracker, client, error = await self.exercise(self.response(
            dict(usage=dict(prompt_tokens=20, completion_tokens=10))))
        self.assertIsInstance(error, KeyError)
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(tracker.spent_effective_tokens, 12)
        self.assertFalse(tracker.has_unaccounted_request)

    async def test_empty_choices_cost_preserved_without_retry(self):
        tracker, client, error = await self.exercise(self.response(
            dict(usage=dict(prompt_tokens=20, completion_tokens=10), choices=[])))
        self.assertIsInstance(error, IndexError)
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(tracker.spent_effective_tokens, 12)

    async def test_uncertain_responses_stop_and_never_retry(self):
        for failure in (httpx.ReadTimeout('fixture'), httpx.ConnectError('fixture'),
                        self.response(text='<html>bad gateway</html>')):
            with self.subTest(kind=type(failure).__name__):
                tracker, client, error = await self.exercise(failure)
                self.assertIsNotNone(error)
                self.assertEqual(client.post.call_count, 1)
                self.assertTrue(tracker.has_unaccounted_request)
                with self.assertRaises(BudgetDenied):
                    await tracker.reserve('next', 1000, 0, 1)

    async def test_http_errors_do_not_guess_budget_exhaustion(self):
        for code, category in ((401, 'AUTHENTICATION'), (403, 'ACCESS_DENIED'),
                               (429, 'RATE_LIMIT'), (503, 'HTTP_ERROR')):
            with self.subTest(code=code):
                tracker, client, error = await self.exercise(self.response({}, status=code))
                self.assertIsInstance(error, APIHTTPError)
                self.assertEqual(error.category, category)
                self.assertEqual(client.post.call_count, 1)
                self.assertTrue(tracker.has_unaccounted_request)

    async def test_truncated_generation_is_accounted_but_not_accepted(self):
        tracker, client, error = await self.exercise(self.response(
            dict(usage=dict(prompt_tokens=20, completion_tokens=10),
                 choices=[dict(finish_reason='length', message=dict(content='partial'))])))
        self.assertIsInstance(error, TruncatedGeneration)
        self.assertEqual(tracker.spent_effective_tokens, 12)
        self.assertFalse(tracker.has_unaccounted_request)
        self.assertEqual(client.post.call_count, 1)

    async def test_request_limit_blocks_next_request(self):
        tracker = BudgetTracker(1000, max_requests=1)
        ticket, _ = await tracker.reserve('a', 1000, 0, 1)
        await tracker.settle(ticket, 0, 1)
        with self.assertRaises(BudgetDenied):
            await tracker.reserve('b', 1000, 0, 1)


if __name__ == '__main__':
    unittest.main()
