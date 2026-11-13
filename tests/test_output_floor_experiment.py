"""Admission floor accounting and negative controls; no network."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from output_floor_benchmark import MinimumOutputTracker
from harness.planner.budget_tracker import BudgetDenied
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.config import HarnessConfig,TaskContext

class FloorTests(unittest.IsolatedAsyncioTestCase):
    def tracker(self,budget,**kw):return MinimumOutputTracker(budget,task_types={'m':'math','s':'search'},floors={'math':32,'search':8},**kw)
    async def test_denial_releases_reserve_and_does_not_consume_request_slot(self):
        t=self.tracker(12,max_requests=1)
        with self.assertRaises(BudgetDenied):await t.reserve('m',12,20,200)
        self.assertEqual(t.remaining,12);self.assertEqual(t.reserved_effective_tokens,0)
        self.assertEqual(t.events[0]['status'],'NOT_SENT');self.assertFalse(t.has_unaccounted_request)
        ticket,cap=await t.reserve('s',12,20,8)
        self.assertEqual(cap,8);await t.settle(ticket,20,2)
        self.assertEqual(t.spent_effective_tokens,4)
    async def test_exact_floor_is_admitted(self):
        t=self.tracker(34);ticket,cap=await t.reserve('m',34,20,200)
        self.assertEqual(cap,32);await t.settle(ticket,10,10)
        self.assertEqual(t.spent_effective_tokens,11)
    async def test_floor_never_exceeds_intentional_requested_cap(self):
        t=self.tracker(10);ticket,cap=await t.reserve('m',10,20,8)
        self.assertEqual(cap,8)
    async def test_failed_admission_never_obtains_transport(self):
        tracker=self.tracker(125)
        config=HarnessConfig(Path('.'),None,'https://fixture.invalid','',initial_budget_tokens=125)
        ctx=TaskContext('m','math','x',1,Path('.'),Path('.'),125,False)
        bridge=OpenJiuwenLLMBridge(config,tracker,ctx)
        def forbidden():raise AssertionError('Transport should not be obtained')
        bridge._get_transport=forbidden
        with self.assertRaises(BudgetDenied):await bridge.complete('qwen3.8-27b-noreason','s','u',max_tokens=200)
        self.assertEqual(bridge.last_attempted_model,'');self.assertEqual(tracker.spent_effective_tokens,0)
    async def test_unknown_usage_still_blocks_every_new_reservation(self):
        t=self.tracker(500);ticket,_=await t.reserve('m',500,20,100);await t.unknown(ticket,'TimeoutError')
        with self.assertRaises(BudgetDenied):await t.reserve('s',500,20,8)
        self.assertTrue(t.has_unaccounted_request);self.assertGreater(t.reserved_effective_tokens,0)
    async def test_below_input_reserve_denial_has_no_ticket(self):
        t=self.tracker(1)
        with self.assertRaises(BudgetDenied):await t.reserve('m',1,100,200)
        self.assertEqual(t.events,[])
    def test_invalid_thresholds_are_rejected(self):
        for value in (True,0,-1,1.5):
            with self.subTest(value=value),self.assertRaises(ValueError):MinimumOutputTracker(100,floors={'math':value})
if __name__=='__main__':unittest.main()
