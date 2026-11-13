"""Experimental output admission floor; production budget logic is unchanged."""
import argparse,asyncio,json
from pathlib import Path
from unittest.mock import patch
import frozen_benchmark as bench
from harness.planner.budget_tracker import BudgetTracker,BudgetDenied

class MinimumOutputTracker(BudgetTracker):
    def __init__(self,*args,task_types=None,floors=None,**kwargs):
        self.task_types=dict(task_types or {})
        self.floors=dict(floors or {})
        if any(type(v) is not int or v<1 for v in self.floors.values()):
            raise ValueError('Invalid output floor')
        super().__init__(*args,**kwargs)
    async def reserve(self,task_id,task_budget,input_estimate,max_output):
        ticket,cap=await super().reserve(task_id,task_budget,input_estimate,max_output)
        minimum=min(max_output,self.floors.get(self.task_types.get(task_id,'other'),1))
        if cap<minimum:
            # No transport has been obtained or called. Release the reservation
            # and leave an explicit zero-cost NOT_SENT event for the audit.
            await self.not_sent(ticket,'OUTPUT_CAP_BELOW_FLOOR')
            raise BudgetDenied(f'Output cap {cap} below experimental floor {minimum}')
        return ticket,cap

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true');args=p.parse_args()
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if plan['admission_arm']=='baseline':return asyncio.run(bench.run(args))
    if plan['admission_arm']!='floor':raise ValueError('Unknown arm')
    # Policy sees only public task type, never expected answers or solvability.
    task_types={}
    for file in (bench.ROOT/plan['tasks']).glob('*/task.json'):
        public=json.loads(file.read_text(encoding='utf-8'));task_types[public['task_id']]=public['task_type']
    class ExperimentTracker(MinimumOutputTracker):
        def __init__(self,*a,**kw):super().__init__(*a,task_types=task_types,floors=plan['output_floors'],**kw)
    with patch('harness.planner.scheduler.BudgetTracker',ExperimentTracker):
        return asyncio.run(bench.run(args))
if __name__=='__main__':raise SystemExit(main())
