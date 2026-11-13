"""H04.33: reserve enough task budget for the existing math request cap."""
import argparse, asyncio, json
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import patch
import frozen_benchmark as bench
from harness.planner.budget_tracker import BudgetTracker
from harness.planner.scheduler import TaskScheduler
KIND=ContextVar('request_budget_task_type',default=None)
class MathReservationTracker(BudgetTracker):
    async def reserve(self,task_id,task_budget,input_estimate,max_output):
        if KIND.get()=='math':
            inp,out,reason=self.usage_for_task(task_id)
            task_budget=max(task_budget,inp/10+out+reason+input_estimate/10+max_output)
        return await super().reserve(task_id,task_budget,input_estimate,max_output)
class MathReservationScheduler(TaskScheduler):
    async def _run_single(self,item):
        token=KIND.set(item['task_type'])
        try:return await super()._run_single(item)
        finally:KIND.reset(token)
async def run(args):
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if plan['concurrency']!=1:raise ValueError('Preregistered concurrency is1')
    with patch.object(bench,'TaskScheduler',MathReservationScheduler),patch('harness.planner.scheduler.BudgetTracker',MathReservationTracker):
        return await bench.run(args)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
