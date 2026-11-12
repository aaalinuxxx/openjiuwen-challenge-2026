"""H04.23 scheduler ordering comparison, isolated from production default."""
import argparse,asyncio,json
from pathlib import Path
import frozen_benchmark as bench
from harness.planner.scheduler import TaskScheduler

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true')
    args=p.parse_args();plan=json.loads(args.plan.read_text(encoding='utf-8'))
    policy=plan['ranking_policy']
    if policy not in ('roi','reward'):raise ValueError('Unknown policy')
    class OrderedScheduler(TaskScheduler):
        def discover_and_rank_tasks(self):
            rows=super().discover_and_rank_tasks()
            if policy=='reward':rows.sort(key=lambda r:(-r['reward'],r['task_id']))
            return rows
    bench.TaskScheduler=OrderedScheduler
    return asyncio.run(bench.run(args))
if __name__=='__main__':raise SystemExit(main())
