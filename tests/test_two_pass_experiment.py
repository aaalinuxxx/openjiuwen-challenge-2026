import asyncio
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from two_pass_benchmark import ACTIVE, RetryTracker, capped_completion, scheduler_type
from harness.config import HarnessConfig, SolveResult
from harness.planner.scheduler import TaskScheduler

class TwoPassTests(unittest.IsolatedAsyncioTestCase):
    async def test_cumulative_retry_allocation_and_usage(self):
        tracker=RetryTracker(1000)
        ticket,_=await tracker.reserve('a',400,100,100)
        await tracker.settle(ticket,100,50)
        token=ACTIVE.set({'task_id':'a','pass':2})
        try:allocation=tracker.allocate_task_budget(expected_cost=100,reward=3)
        finally:ACTIVE.reset(token)
        self.assertEqual(allocation,310)
        ticket,cap=await tracker.reserve('a',allocation,100,500)
        self.assertEqual(cap,240)
        await tracker.settle(ticket,100,100)
        self.assertEqual(tracker.spent_effective_tokens,170)
        self.assertEqual(tracker.usage_for_task('a'),(200,150,0))

    async def test_cap_only_first_pass(self):
        seen=[]
        async def original(bridge,model,system,user,max_tokens,temperature):
            seen.append(max_tokens);return 'ok',1,1,0
        complete=capped_completion(original,{'math':64})
        for phase in (1,2):
            state={'task_id':'a','task_type':'math','pass':phase,'requests':[]}
            token=ACTIVE.set(state)
            try:await complete(None,'model','system','user',200)
            finally:ACTIVE.reset(token)
        self.assertEqual(seen,[64,200])
        self.assertIsNone(ACTIVE.get())

    async def exercise(self,budget=1000,unknown=False):
        with tempfile.TemporaryDirectory() as d:
            config=HarnessConfig(Path(d),None,'','',max_concurrency=1,initial_budget_tokens=budget,execution_engine='direct')
            scheduler=scheduler_type({'math':64})(config)
            scheduler.budget_tracker=RetryTracker(budget)
            statuses={'a':'TRUNCATED','b':'SOLVED','c':'UNSOLVABLE','d':'UNKNOWN','e':'BUDGET_EXCEEDED','f':'FAILED'}
            items=[dict(task_id=n,task_type='math',reward=2) for n in statuses]
            calls=[]
            async def fake_single(owner,item):
                state=ACTIVE.get(); n=item['task_id'];calls.append((n,state['pass']))
                if n in ('a','f'):
                    state['requests'].append(dict(requested_cap=200,first_cap=64 if state['pass']==1 else 200))
                    ticket,cap=await owner.budget_tracker.reserve(n,1000,10,1)
                    if unknown and n=='a':await owner.budget_tracker.unknown(ticket,'timeout')
                    else:await owner.budget_tracker.settle(ticket,10,1)
                result=SolveResult(n,'SOLVED' if state['pass']==2 else statuses[n],answer='1' if state['pass']==2 or n=='b' else None)
                owner.results[n]=asdict(result);return result
            async def fake_all(owner):
                for item in items:
                    if unknown and owner.budget_tracker.proxy_exhausted:break
                    await owner._run_single(item)
                return {}
            with patch.object(TaskScheduler,'_run_single',fake_single),patch.object(TaskScheduler,'run_all',fake_all):
                result=await scheduler.run_all()
            return result,calls

    async def test_retry_only_observed_failures_once(self):
        result,calls=await self.exercise()
        self.assertEqual([n for n,p in calls if p==2],['a','f'])
        self.assertEqual(result['solved_count'],3)
        self.assertEqual(result['effective_tokens_spent'],8)
        self.assertEqual(len(result['budget_state']['events']),4)

    async def test_insufficient_reserve_skips_paid_repeat(self):
        result,calls=await self.exercise(budget=100)
        self.assertFalse(any(p==2 for n,p in calls))
        self.assertEqual(result['effective_tokens_spent'],4)

    async def test_unknown_cost_stops_retries(self):
        result,calls=await self.exercise(unknown=True)
        self.assertFalse(any(p==2 for n,p in calls))
        self.assertTrue(result['budget_state']['has_unaccounted_request'])
        self.assertGreater(result['budget_state']['reserved_effective_tokens'],0)

if __name__=='__main__':unittest.main()
