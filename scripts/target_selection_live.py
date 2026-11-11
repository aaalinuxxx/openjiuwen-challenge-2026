"""E59 controls and E60 paired live target-selection experiment."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api_settings import load_settings
from multimodule_live import populate, check, write, digest
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.coding_solver import solve_coding_task
from harness.agents.coding_target import select_coding_target
from harness.workflow_runner import OpenJiuwenTaskRunner

FIXTURE = ROOT/'experiments/E59_target_selection'

def legacy():
    spec=importlib.util.spec_from_file_location('frozen_legacy_coding',FIXTURE/'legacy_coding_solver.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.solve_coding_task

def validate(cases):
    rows=[]
    with tempfile.TemporaryDirectory(prefix='oj-target-oracle-') as temp:
        for case in cases:
            root=Path(temp)/case['id']
            populate(root,case['files'])
            before=check(root,case['files'],case['checks'])
            (root/case['target']).write_text(case['reference'],encoding='utf-8')
            after=check(root,case['files'],case['checks'])
            rows.append(dict(case=case['id'],original=before,reference=after))
    controls=[]
    for instruction,names,expected in json.loads((FIXTURE/'selector_controls.json').read_text(encoding='utf-8')):
        files=[Path(n) for n in names]
        requested=re.findall(r'\b(?:fix|repair|correct|update)\s+(?:the\s+)?(?:bugs?\s+in\s+)?`?([A-Za-z_][A-Za-z0-9_]*\.py)\b',instruction,re.I)
        matches=[p for p in files if p.name in requested]
        old=matches[0] if len(matches)==1 else (files[0] if len(files)==1 and not requested else None)
        new=select_coding_target(instruction,files)
        controls.append(dict(instruction=instruction,expected=expected,old=old.name if old else None,new=new.name if new else None))
    report=dict(api_calls=0,oracle_passed=all(not r['original']['passed'] and r['reference']['passed'] for r in rows),
                rows=rows,controls=controls,old_correct=sum(r['old']==r['expected'] for r in controls),
                new_correct=sum(r['new']==r['expected'] for r in controls),total=len(controls))
    write(FIXTURE/'local_validation.json',report)
    if not report['oracle_passed'] or report['new_correct']!=len(controls): raise ValueError('Validation failed')
    print(json.dumps({k:report[k] for k in ('api_calls','oracle_passed','old_correct','new_correct','total')}),flush=True)

async def run(live):
    plan=json.loads((FIXTURE/'live_plan.json').read_text(encoding='utf-8'))
    for name,sha in plan['frozen_hashes'].items():
        if digest(ROOT/name)!=sha: raise ValueError('Frozen source changed: '+name)
    cases=json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8'))
    old_solver=legacy()
    settings=load_settings() if live else dict(LLM_BASE_URL='https://fixture.invalid/v1',LLM_API_KEY='offline')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/('E60_target_'+('live_' if live else 'preflight_')+stamp)
    if live:
        with (FIXTURE/'live_started.json').open('x',encoding='utf-8') as file:
            json.dump(dict(directory=directory.name,started_at=stamp),file)
    directory.mkdir()
    tracker=BudgetTracker(plan['budget'],directory/'budget.json',max_requests=plan['max_calls'])
    original_transport=OpenJiuwenLLMBridge._get_transport
    count=0
    rows,recording_errors=[],[]
    report=dict(mode='LIVE' if live else 'PREFLIGHT_REFERENCE_PATCHES',status='RUNNING',scope=plan['scope'],
                plan_sha256=digest(FIXTURE/'live_plan.json'),source_hashes=plan['frozen_hashes'],rows=rows,recording_errors=recording_errors)
    def persist():
        report['budget']=tracker.snapshot()
        report['real_api_attempts']=count if live else 0
        report['known_effective_tokens']=tracker.spent_effective_tokens if live else 0
        write(directory/'report.json',report)
    def recording_transport(bridge):
        transport=original_transport(bridge) if live else None
        async def send(payload):
            nonlocal count
            count+=1
            index=count
            write(directory/f'request_{index:02d}.json',dict(task_id=bridge.task_id,payload=payload,mode=report['mode']))
            if live:
                data=await transport(payload)
            else:
                case=next(c for c in cases if c['id']==bridge.task_id.split('__')[0])
                data=dict(usage=dict(prompt_tokens=0,completion_tokens=0),
                          choices=[dict(message=dict(content=case['reference']),finish_reason='stop')])
            try:
                write(directory/f'response_{index:02d}.json',dict(task_id=bridge.task_id,response=data))
            except OSError as error:
                recording_errors.append(dict(request=index,error_type=type(error).__name__))
            return data
        return send
    persist()
    with tempfile.TemporaryDirectory(prefix='oj-target-pairs-') as temp:
        config=HarnessConfig(Path(temp),None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],
                             initial_budget_tokens=plan['budget'],max_concurrency=1,request_timeout_sec=60,workflow_timeout_sec=180)
        runner=OpenJiuwenTaskRunner(config,tracker)
        with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording_transport):
            for i,case in enumerate(cases):
                for order,arm in enumerate(['old','new'] if i%2==0 else ['new','old']):
                    if tracker.has_unaccounted_request or tracker.proxy_exhausted: break
                    task_id=case['id']+'__'+arm
                    root=Path(temp)/task_id
                    populate(root,case['files'])
                    initial={name:digest(root/name) for name in case['files']}
                    ctx=TaskContext(task_id,'coding',case['instruction'],2,root,root,plan['per_task_budget'],False)
                    before=count
                    with patch('harness.agents.base_harness.solve_coding_task',old_solver if arm=='old' else solve_coding_task):
                        result=await runner.run(ctx)
                    answer_file=root/'answer.txt'
                    answer=answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
                    validation=check(root,case['files'],case['checks'])
                    unchanged=all(digest(root/n)==h for n,h in initial.items() if n!=case['target'])
                    added=sorted(p.name for p in root.iterdir() if p.name not in case['files'] and p.name!='answer.txt')
                    delivered=result.status=='SOLVED' and answer=='DONE'
                    solved=delivered and validation['passed'] and unchanged and not added
                    row=dict(case=case['id'],arm=arm,order_in_pair=order,status=result.status,answer=answer,solved=solved,
                             wrong_delivery=delivered and not solved,validation=validation,unchanged_non_target=unchanged,
                             unexpected_files=added,original_hashes=initial,final_hashes={n:digest(root/n) for n in case['files']},
                             calls=count-before,effective_cost=result.effective_cost,result=asdict(result),workflow=runner.runs[-1])
                    artifact=directory/task_id
                    artifact.mkdir()
                    populate(artifact/'original',case['files'])
                    (artifact/'final').mkdir()
                    for name in case['files']: shutil.copyfile(root/name,artifact/'final'/name)
                    if answer_file.exists(): shutil.copyfile(answer_file,artifact/'final'/'answer.txt')
                    write(artifact/'validation.json',row)
                    rows.append(row)
                    persist()
                    print(json.dumps({k:row[k] for k in ('case','arm','status','solved','calls','effective_cost')},ensure_ascii=False),flush=True)
                if tracker.has_unaccounted_request or tracker.proxy_exhausted: break
    metrics={}
    for arm in ('old','new'):
        subset=[r for r in rows if r['arm']==arm]
        metrics[arm]=dict(attempted=len(subset),solved=sum(r['solved'] for r in subset),
                          wrong_deliveries=sum(r['wrong_delivery'] for r in subset),
                          calls=sum(r['calls'] for r in subset),effective_tokens=round(sum(r['effective_cost'] for r in subset),3))
    report['metrics']=metrics
    report['prior_ledgers_unchanged']=all(digest(ROOT/p)==plan['frozen_hashes'][p] for p in plan['prior_unknown_ledgers'])
    report['status']='STOPPED_UNKNOWN_COST' if tracker.has_unaccounted_request else ('COMPLETED' if len(rows)==8 else 'INCOMPLETE')
    if not live:
        report['preflight_passed']=(len(rows)==8 and count==5 and not recording_errors
            and metrics['old']['solved']==1 and metrics['new']['solved']==4 and all(r['unchanged_non_target'] for r in rows))
    persist()
    print(json.dumps({k:report[k] for k in ('status','metrics','real_api_attempts','known_effective_tokens','prior_ledgers_unchanged')}),flush=True)
    if not live: print('preflight_passed:',report['preflight_passed'],flush=True)
    print('Report:',directory/'report.json',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--validate',action='store_true')
    args=parser.parse_args()
    if args.validate: validate(json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8')))
    else: asyncio.run(run(args.live))
