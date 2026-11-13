"""Factorial ranking/admission benchmark; reuses the previously tested floor."""
import argparse,asyncio,json
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import frozen_benchmark as bench
from harness.planner.scheduler import TaskScheduler
from output_floor_benchmark import MinimumOutputTracker

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true');args=p.parse_args()
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if plan['ranking_policy'] not in ('roi','calibrated') or plan['admission_arm'] not in ('baseline','floor'):raise ValueError('Unknown policy')
    class OrderedScheduler(TaskScheduler):
        def discover_and_rank_tasks(self):
            rows=super().discover_and_rank_tasks()
            if plan['ranking_policy']=='calibrated':
                for row in rows:row['roi']=row['reward']*row['p_solv']/plan['median_costs'][row['task_type']]
                rows.sort(key=lambda r:(-r['roi'],-r['reward'],r['expected_cost'],r['task_id']))
            return rows
    with ExitStack() as stack:
        stack.enter_context(patch.object(bench,'TaskScheduler',OrderedScheduler))
        if plan['admission_arm']=='floor':
            types={}
            for file in (bench.ROOT/plan['tasks']).glob('*/task.json'):
                public=json.loads(file.read_text(encoding='utf-8'));types[public['task_id']]=public['task_type']
            class ExperimentTracker(MinimumOutputTracker):
                def __init__(self,*a,**kw):super().__init__(*a,task_types=types,floors=plan['output_floors'],**kw)
            stack.enter_context(patch('harness.planner.scheduler.BudgetTracker',ExperimentTracker))
        return asyncio.run(bench.run(args))
if __name__=='__main__':raise SystemExit(main())
