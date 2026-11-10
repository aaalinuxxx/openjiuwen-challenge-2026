"""Full scheduler/bridge controls with a fake HTTP transport; never uses API.

The unchanged scenarios run before/after G0 budget fixes. Synthetic usage is
for accounting invariants only, never a cost or model-quality estimate.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import HarnessConfig

STATE = dict(mode='normal', calls=0, caps=[])


class Response:
    def __init__(self, cap): self.cap=cap
    def raise_for_status(self): pass
    def json(self):
        if STATE['mode']=='bad_content':
            return dict(usage=dict(prompt_tokens=20,completion_tokens=10))
        return dict(usage=dict(prompt_tokens=0,completion_tokens=min(120,self.cap)),
                    choices=[dict(message=dict(content='OK'))])


class Client:
    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def post(self, url, headers, json):
        STATE['calls']+=1
        STATE['caps'].append(json['max_tokens'])
        await asyncio.sleep(0.01)
        if STATE['mode']=='unknown_cost': raise OSError('Synthetic transport failure')
        return Response(json['max_tokens'])


async def run(label):
    scenarios=[('parallel',300,5,'normal',5,False),
               ('free_at_zero',0,1,'normal',1,True),
               ('bad_content',1000,1,'bad_content',1,False),
               ('unknown_cost',1000,1,'unknown_cost',2,True)]
    rows=[]
    with patch.dict(sys.modules,{'httpx':SimpleNamespace(AsyncClient=Client)}):
        from harness.planner.scheduler import TaskScheduler
        with tempfile.TemporaryDirectory(prefix='oj-budget-controls-') as tmp:
            for name,budget,concurrency,mode,remote_count,add_local in scenarios:
                folder=Path(tmp)/name
                folder.mkdir()
                for i in range(remote_count):
                    work=folder/f'remote_{i}';work.mkdir()
                    (work/'task.json').write_text(json.dumps(dict(task_id=work.name,task_type='other',
                        instruction='Return OK.',reward=1)),encoding='utf-8')
                if add_local:
                    work=folder/'local';work.mkdir()
                    (work/'task.json').write_text(json.dumps(dict(task_id='local',task_type='math',
                        instruction='A warehouse starts with 10 boxes. It receives 2 boxes. How many boxes does it have at the end?',
                        reward=1)),encoding='utf-8')
                STATE.update(mode=mode,calls=0,caps=[])
                config=HarnessConfig(folder,None,'https://fixture.invalid/v1','fixture-only',
                                     max_concurrency=concurrency,initial_budget_tokens=budget,execution_engine='direct')
                scheduler=TaskScheduler(config)
                summary=await scheduler.run_all()
                rows.append(dict(case=name,summary=summary,transport_calls=STATE['calls'],
                                 output_caps=STATE['caps'],
                                 local_answer=(folder/'local'/'answer.txt').read_text().strip()
                                   if (folder/'local'/'answer.txt').exists() else None))
    sources=list((ROOT/'harness').rglob('*.py'))+[Path(__file__)]
    report=dict(label=label,scope='synthetic HTTP; full scheduler/bridge; no real tokens or model quality',
                api_calls=0,scenario_sha256=hashlib.sha256(json.dumps(scenarios).encode()).hexdigest(),rows=rows,
                source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    path=ROOT/'experiments'/f'{label}.json'
    with path.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
    print(json.dumps(rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);a=p.parse_args()
    if not a.label.replace('_','').isalnum(): p.error('Invalid label')
    asyncio.run(run(a.label))
