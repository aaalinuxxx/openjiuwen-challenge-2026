import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from math_budget_benchmark import KIND,MathReservationTracker
from harness.planner.budget_tracker import BudgetDenied
class MathReservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_math_gets_requested_cap_with_global_room(self):
        tracker=MathReservationTracker(1000);token=KIND.set('math')
        try:ticket,cap=await tracker.reserve('a',185,1400,200)
        finally:KIND.reset(token)
        self.assertEqual(cap,200)
        self.assertEqual(tracker.events[ticket]['task_limit_units'],3400)
    async def test_other_types_keep_original_task_limit(self):
        tracker=MathReservationTracker(1000);token=KIND.set('data_analysis')
        try:ticket,cap=await tracker.reserve('a',185,1400,200)
        finally:KIND.reset(token)
        self.assertEqual(cap,45)
    async def test_global_budget_still_caps_request(self):
        tracker=MathReservationTracker(185);token=KIND.set('math')
        try:ticket,cap=await tracker.reserve('a',185,1400,200)
        finally:KIND.reset(token)
        self.assertEqual(cap,45)
    async def test_cumulative_usage_never_reset(self):
        tracker=MathReservationTracker(1000);token=KIND.set('math')
        try:
            ticket,_=await tracker.reserve('a',185,1400,200)
            await tracker.settle(ticket,100,50)
            ticket,cap=await tracker.reserve('a',185,1400,200)
        finally:KIND.reset(token)
        self.assertEqual(cap,200);self.assertEqual(tracker.spent_effective_tokens,60)
        self.assertEqual(tracker.events[ticket]['task_limit_units'],4000)
    async def test_unknown_cost_blocks_new_request(self):
        tracker=MathReservationTracker(1000);token=KIND.set('math')
        try:
            ticket,_=await tracker.reserve('a',185,1400,200)
            await tracker.unknown(ticket,'timeout')
            with self.assertRaises(BudgetDenied):await tracker.reserve('b',185,1400,200)
        finally:KIND.reset(token)
        self.assertTrue(tracker.has_unaccounted_request)
if __name__=='__main__':unittest.main()
