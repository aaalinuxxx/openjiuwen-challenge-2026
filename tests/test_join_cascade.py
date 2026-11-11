import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from harness.agents.base_harness import solve_task
from harness.agents.join_cascade import solve_join_cascade_task
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker

GOOD = dict(left="a.csv",right="b.csv",left_key="key",right_key="key",join="inner",filter=None,
            aggregate=dict(op="sum",side="left",column="value"))

class JoinCascadeControls(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,responses,global_cap=5000,task_cap=1200,max_calls=3,consume_reservation=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"a.csv").write_text("key,value\nx,2\n")
            (root/"b.csv").write_text("key,value\nx,3\n")
            config=HarnessConfig(root,None,"https://fixture.invalid/v1","offline",initial_budget_tokens=global_cap)
            ctx=TaskContext("cascade","data_analysis","Read a.csv and b.csv. Join on key and sum a.value.",2,root,root,task_cap,False)
            tracker=BudgetTracker(global_cap,max_requests=max_calls)
            payloads=[]
            async def send(payload):
                index=len(payloads)
                payloads.append(payload)
                item=responses[index]
                if isinstance(item,Exception): raise item
                if consume_reservation:
                    inp=tracker.events[-1]["input_token_estimate"]
                    out=payload["max_tokens"]
                else:
                    inp,out=(50,10) if index==0 else (70,20)
                return dict(usage=dict(prompt_tokens=inp,completion_tokens=out),
                            choices=[dict(message=dict(content=item),finish_reason="stop")])
            with patch("harness.agents.base_harness.solve_data_task",solve_join_cascade_task):
                result=await solve_task(ctx,config,tracker,transport=send)
            return result,tracker,payloads

    async def test_supported_plan_stops_after_one_request(self):
        result,tracker,payloads=await self.invoke([json.dumps(GOOD)])
        self.assertEqual((result.status,result.answer),("SOLVED","2"))
        self.assertEqual(len(payloads),1)
        self.assertEqual(result.effective_cost,15)

    async def test_explicit_unsupported_uses_same_ledger_and_counts_both(self):
        result,tracker,payloads=await self.invoke(["UNSUPPORTED","print(7)"])
        self.assertEqual((result.status,result.answer),("SOLVED","7"))
        self.assertEqual(len(payloads),2)
        self.assertEqual(result.effective_cost,42)
        self.assertEqual(tracker.spent_effective_tokens,42)
        self.assertEqual(tracker.usage_for_task("cascade"),(120,30,0))

    async def test_malformed_and_invalid_plans_do_not_fallback(self):
        invalid={**GOOD,"left_key":"absent"}
        for text in ("not-json",json.dumps(invalid),'{"left":"a.csv"}'):
            result,tracker,payloads=await self.invoke([text])
            self.assertEqual(result.status,"UNKNOWN")
            self.assertEqual(len(payloads),1)
            self.assertEqual(result.effective_cost,15)

    async def test_request_cap_blocks_second_send_without_losing_first_usage(self):
        result,tracker,payloads=await self.invoke(["UNSUPPORTED"],max_calls=1)
        self.assertEqual(result.status,"BUDGET_EXCEEDED")
        self.assertEqual(len(payloads),1)
        self.assertEqual(result.effective_cost,15)
        self.assertFalse(tracker.has_unaccounted_request)

    async def test_global_and_task_limits_block_second_send(self):
        for global_cap,task_cap in ((500,1200),(5000,500)):
            result,tracker,payloads=await self.invoke(["UNSUPPORTED"],global_cap,task_cap,consume_reservation=True)
            self.assertEqual(result.status,"BUDGET_EXCEEDED")
            self.assertEqual(len(payloads),1)
            self.assertGreater(result.effective_cost,0)
            self.assertLessEqual(result.effective_cost,500)
            self.assertFalse(tracker.has_unaccounted_request)
            self.assertFalse(tracker.proxy_exhausted)

    async def test_unknown_first_cost_stops_before_fallback(self):
        result,tracker,payloads=await self.invoke([TimeoutError()])
        self.assertEqual(result.status,"ACCOUNTING_UNKNOWN")
        self.assertEqual(len(payloads),1)
        self.assertTrue(tracker.has_unaccounted_request)
        self.assertEqual(tracker.spent_effective_tokens,0)
        self.assertGreater(tracker.reserved_effective_tokens,0)

    async def test_unknown_second_cost_keeps_first_known_usage(self):
        result,tracker,payloads=await self.invoke(["UNSUPPORTED",TimeoutError()])
        self.assertEqual(result.status,"ACCOUNTING_UNKNOWN")
        self.assertEqual(len(payloads),2)
        self.assertEqual(result.effective_cost,15)
        self.assertEqual(tracker.spent_effective_tokens,15)
        self.assertTrue(tracker.has_unaccounted_request)
        with self.assertRaises(Exception):
            await tracker.reserve("cascade",1200,100,400)
