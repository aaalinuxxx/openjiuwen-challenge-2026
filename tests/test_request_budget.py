import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker, BudgetDenied
from harness.agents.base_harness import OpenJiuwenLLMBridge, solve_task, parse_usage


class RequestBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_reservations_cannot_spend_same_remainder(self):
        tracker=BudgetTracker(300)
        reservations=await asyncio.gather(*(tracker.reserve(str(i),100,0,80) for i in range(5)),return_exceptions=True)
        admitted=[r for r in reservations if isinstance(r,tuple)]
        self.assertEqual(sorted(cap for _,cap in admitted),[60,80,80,80])
        self.assertEqual(tracker.reserved_effective_tokens,300)
        self.assertEqual(sum(isinstance(r,BudgetDenied) for r in reservations),1)
        for ticket,cap in admitted: await tracker.settle(ticket,0,cap)
        self.assertEqual(tracker.spent_effective_tokens,300)
        self.assertEqual(tracker.reserved_effective_tokens,0)

    async def test_per_task_cap_includes_previous_requests(self):
        tracker=BudgetTracker(100)
        first,cap=await tracker.reserve('a',10,20,20)
        self.assertEqual(cap,8)
        await tracker.settle(first,10,2)
        second,cap=await tracker.reserve('a',10,20,20)
        self.assertEqual(cap,5)
        await tracker.settle(second,20,5)
        self.assertEqual(tracker.spent_effective_tokens,10)
        with self.assertRaises(BudgetDenied): await tracker.reserve('a',10,0,1)

    async def test_unknown_cost_retains_hold_stops_new_but_settles_inflight(self):
        tracker=BudgetTracker(100)
        a,_=await tracker.reserve('a',100,0,40)
        b,_=await tracker.reserve('b',100,0,40)
        await tracker.unknown(a,'TimeoutError')
        with self.assertRaises(BudgetDenied): await tracker.reserve('c',100,0,1)
        await tracker.settle(b,10,20)
        self.assertEqual(tracker.spent_effective_tokens,21)
        self.assertEqual(tracker.reserved_effective_tokens,40)
        self.assertTrue(tracker.has_unaccounted_request)

    async def test_underestimated_input_stops_after_recording_actual_cost(self):
        tracker=BudgetTracker(10)
        ticket,_=await tracker.reserve('a',10,0,10)
        await tracker.settle(ticket,100,10)
        self.assertEqual(tracker.spent_effective_tokens,20)
        self.assertTrue(tracker.proxy_exhausted)
        self.assertTrue(tracker.events[0]['reserve_exceeded'])

    async def test_paid_attempt_survives_later_failure_and_journal_has_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            tracker=BudgetTracker(1000,directory/'audit.json')
            config=HarnessConfig(directory,None,'https://fixture.invalid','secret-fixture')
            ctx=TaskContext('a','other','x',1,directory,directory,1000,False)
            calls=0
            async def transport(payload):
                nonlocal calls
                calls+=1
                if calls==2: raise OSError('Synthetic unknown cost')
                return dict(usage=dict(prompt_tokens=20,completion_tokens=10),choices=[dict(message=dict(content='OK'))])
            async def solver(ctx,bridge):
                await bridge.complete('qwen3.8-27b-noreason','x','y',20)
                await bridge.complete('qwen3.8-27b-noreason','x','y',20)
            with patch('harness.agents.base_harness.solve_fallback_task',solver):
                result=await solve_task(ctx,config,tracker,transport)
            self.assertEqual(result.effective_cost,12)
            self.assertEqual(result.status,'ACCOUNTING_UNKNOWN')
            journal=(directory/'audit.json').read_text()
            self.assertNotIn('secret-fixture',journal)
            self.assertTrue(json.loads(journal)['has_unaccounted_request'])

    async def test_cancellation_retains_uncertain_reservation(self):
        tracker=BudgetTracker(1000)
        config=HarnessConfig(Path('.'),None,'https://fixture.invalid','fixture')
        async def transport(payload): raise asyncio.CancelledError()
        bridge=OpenJiuwenLLMBridge(config,tracker,transport=transport)
        with self.assertRaises(asyncio.CancelledError):
            await bridge.complete('qwen3.8-27b-noreason','x','y',20)
        self.assertTrue(tracker.has_unaccounted_request)

    async def test_partially_paid_solver_is_not_restarted_on_reservation_conflict(self):
        tracker=BudgetTracker(300)
        await tracker.reserve('other',300,5,179)
        config=HarnessConfig(Path('.'),None,'https://fixture.invalid','fixture')
        ctx=TaskContext('a','other','x',1,Path('.'),Path('.'),1000,False)
        calls=0
        async def transport(payload):
            nonlocal calls
            calls+=1
            return dict(usage=dict(prompt_tokens=0,completion_tokens=2),choices=[dict(message=dict(content='OK'))])
        async def solver(ctx,bridge):
            # Same prompt reserve as the benchmark (1179 input-token estimate).
            await bridge.complete('qwen3.8-27b-noreason','x'*155,'',20)
            await bridge.complete('qwen3.8-27b-noreason','x'*155,'',20)
        with patch('harness.agents.base_harness.solve_fallback_task',solver):
            result=await solve_task(ctx,config,tracker,transport)
        self.assertEqual(result.status,'BUDGET_EXCEEDED')
        self.assertEqual(calls,1)
        self.assertEqual(result.effective_cost,2)

    async def test_reasoning_model_requires_explicit_contract(self):
        tracker=BudgetTracker(1000)
        config=HarnessConfig(Path('.'),None,'https://fixture.invalid','fixture')
        bridge=OpenJiuwenLLMBridge(config,tracker)
        with self.assertRaises(BudgetDenied): await bridge.complete('qwen3.8-27b','x','y')
        self.assertEqual(tracker.events,[])

    def test_explicit_reasoning_modes_and_invalid_usage(self):
        data=dict(usage=dict(prompt_tokens=20,completion_tokens=10,completion_tokens_details=dict(reasoning_tokens=4)))
        self.assertEqual(parse_usage(data,'included'),(20,6,4))
        self.assertEqual(parse_usage(data,'separate'),(20,10,4))
        with self.assertRaises(ValueError): parse_usage(data)
        with self.assertRaises(ValueError): parse_usage(dict(usage=dict(prompt_tokens=True,completion_tokens=1)))


if __name__=='__main__': unittest.main()
