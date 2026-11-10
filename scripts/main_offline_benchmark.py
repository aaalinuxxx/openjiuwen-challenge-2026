"""Run the actual scheduler on cleaned public samples at zero API budget."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import HarnessConfig
from harness.planner.scheduler import TaskScheduler


async def main():
    source=ROOT.parent/'task-dir'/'task-dir'
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='oj-main-offline-') as tmp:
        directory=Path(tmp)/'tasks'
        directory.mkdir()
        truths={}
        for task in source.glob('*/task.json'):
            data=json.loads(task.read_text(encoding='utf-8'))
            truths[task.parent.name]=data
            target=directory/task.parent.name
            shutil.copytree(task.parent,target)
            (target/'task.json').write_text(json.dumps({k:v for k,v in data.items() if k not in ('expected','unsolvable')}),encoding='utf-8')
            for answer in target.rglob('answer.txt'): answer.unlink()
        scheduler=TaskScheduler(HarnessConfig(directory,None,'https://fixture.invalid','fixture',initial_budget_tokens=0,execution_engine='direct'))
        summary=await scheduler.run_all()
        rows=[]
        for name,truth in truths.items():
            path=directory/name/'answer.txt'
            answer=path.read_text(encoding='utf-8').strip() if path.exists() else None
            rows.append(dict(task_id=name,answer=answer,correct=truth['task_type']!='coding' and answer==str(truth['expected']),reward=truth['reward']))
    assert all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in originals.items())
    report=dict(scope='actual scheduler, cleaned public samples, zero API budget, coding not repaired',
                summary=summary,rows=rows,correct=sum(r['correct'] for r in rows),
                score=sum(r['reward'] for r in rows if r['correct']),
                source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'harness').rglob('*.py')})
    with (ROOT/'experiments'/'E26_main_zero_budget.json').open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_hashes')}))
    assert report['correct']==6 and report['score']==16 and not summary['budget_state']['events']


if __name__=='__main__': asyncio.run(main())
