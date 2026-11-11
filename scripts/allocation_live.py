"""E79/E80: shared total budget, different search/data task-budget floors."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api_settings import load_settings
from main_offline_benchmark import hashes,verify_coding
from multimodule_live import write,digest
from harness.config import HarnessConfig
from harness.planner.scheduler import TaskScheduler
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.join_or import join_or_route
FIXTURE=ROOT/'experiments/E79_budget_allocation'
TASK_FIXTURE=ROOT/'experiments/E77_mixed_integration'

def summarize(rows):
    return dict(total=len(rows),solvable=sum(not r['unsolvable'] for r in rows),
                correct=sum(r['verified_solution'] for r in rows),
                score=sum(r['reward'] for r in rows if r['verified_solution']),
                max_score=sum(r['reward'] for r in rows if not r['unsolvable']),
                wrong_answers=sum(r['answer'] is not None and not r['verified_solution'] for r in rows),
                justified_refusals=sum(r['justified_refusal'] for r in rows),
                false_refusals=sum(not r['unsolvable'] and r['status'] in ('UNSOLVABLE','SKIPPED') for r in rows),
                truncations=sum(r['status']=='TRUNCATED' for r in rows))

async def run(live):
    plan=json.loads((FIXTURE/'live_plan.json').read_text(encoding='utf-8'))
    for name,sha in plan['frozen_hashes'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen source changed: '+name)
    fixture=json.loads((TASK_FIXTURE/'fixture_validation.json').read_text(encoding='utf-8'))
    if hashes(TASK_FIXTURE/'tasks')!=fixture['fixtures_sha256']:raise ValueError('Fixture changed')
    labels=json.loads((TASK_FIXTURE/'labels.json').read_text(encoding='utf-8'))
    settings=load_settings() if live else dict(LLM_BASE_URL='https://fixture.invalid/v1',LLM_API_KEY='offline')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/('E80_allocation_'+('live_' if live else 'offline_')+stamp)
    if live:
        with (FIXTURE/'live_started.json').open('x',encoding='utf-8') as f:json.dump(dict(directory=directory.name,started_at=stamp),f)
    directory.mkdir()
    report=dict(mode='LIVE' if live else 'OFFLINE_ZERO_BUDGET',status='RUNNING',plan_sha256=digest(FIXTURE/'live_plan.json'),arms={},recording_errors=[])
    write(directory/'report.json',report)
    original_transport=OpenJiuwenLLMBridge._get_transport
    for arm,enabled in [('baseline',True),('candidate',True)]:
        arm_dir=directory/arm;arm_dir.mkdir()
        requests=0
        with tempfile.TemporaryDirectory(prefix='oj-mixed-') as temp:
            taskroot=Path(temp)/'tasks'
            shutil.copytree(TASK_FIXTURE/'tasks',taskroot)
            initial={n:hashes(taskroot/n) for n in labels}
            protected={n:{p.relative_to(taskroot/n):p.read_bytes() for p in (taskroot/n).rglob('test_*.py')} for n in labels}
            for n in labels:
                public=json.loads((taskroot/n/'task.json').read_text(encoding='utf-8'))
                if set(public)!={'task_id','task_type','instruction','reward'}:raise ValueError('Unexpected public metadata')
            config=HarnessConfig(taskroot,None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],
                max_concurrency=1,initial_budget_tokens=plan['budget_per_arm'] if live else 0,
                max_api_calls=plan['max_calls_per_arm'] if live else 0,
                budget_audit_path=arm_dir/'budget.json',experimental_joins=enabled,
                search_min_task_budget=plan['profiles'][arm]['search_min_task_budget'],
                data_min_task_budget=plan['profiles'][arm]['data_min_task_budget'])
            class RecordingScheduler(TaskScheduler):
                async def _run_single(self,item):
                    result=await super()._run_single(item)
                    write(arm_dir/'progress.json',dict(results=self.results,budget=self.budget_tracker.snapshot(),workflow_runs=self.task_runner.runs))
                    print(json.dumps(dict(arm=arm,task_id=result.task_id,status=result.status,cost=result.effective_cost)),flush=True)
                    return result
            scheduler=RecordingScheduler(config)
            ranked=scheduler.discover_and_rank_tasks()
            write(arm_dir/'ranking.json',[dict(task_id=r['task_id'],roi=r['roi'],expected_cost=r['expected_cost'],reward=r['reward']) for r in ranked])
            routes={n:join_or_route(taskroot/n,t['instruction']) for n,t in labels.items() if t['task_type']=='data_analysis'}
            def recording_transport(bridge):
                if not live:raise AssertionError('Offline transport forbidden')
                transport=original_transport(bridge)
                async def send(payload):
                    nonlocal requests
                    requests+=1;idx=requests
                    write(arm_dir/f'request_{idx:02d}.json',dict(task_id=bridge.task_id,payload=payload))
                    data=await transport(payload)
                    try:write(arm_dir/f'response_{idx:02d}.json',dict(task_id=bridge.task_id,response=data))
                    except OSError as e:report['recording_errors'].append(dict(arm=arm,index=idx,error_type=type(e).__name__))
                    return data
                return send
            with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording_transport):
                summary=await scheduler.run_all()
            rows=[]
            for name,truth in labels.items():
                root=taskroot/name
                answer_path=root/'answer.txt'
                answer=answer_path.read_text(encoding='utf-8').strip() if answer_path.exists() else None
                result=summary['task_results'].get(name,{})
                status=result.get('status','SKIPPED' if name in summary['skipped_tasks'] else 'NOT_RUN')
                final=hashes(root)
                changed=[p for p,h in initial[name].items() if final.get(p)!=h]
                unexpected=[p for p in final if p not in initial[name] and p!='answer.txt']
                allowed={'mylib.py'} if truth['task_type']=='coding' else set()
                integrity=not unexpected and not(set(changed)-allowed)
                correct=not truth['unsolvable'] and answer is not None and answer==str(truth['expected'])
                if truth['group']=='E75_pilot' and answer is not None:
                    try:correct=Decimal(answer).is_finite() and Decimal(answer)==Decimal(truth['expected'])
                    except InvalidOperation:correct=False
                if truth['task_type']=='coding':correct=not truth['unsolvable'] and verify_coding(root,protected[name],answer)
                correct=bool(correct and status=='SOLVED' and integrity)
                events=[e for e in summary['budget_state']['events'] if e['task_id']==name and e['status']!='NOT_SENT']
                row=dict(task_id=name,task_type=truth['task_type'],group=truth['group'],reward=truth['reward'],
                    unsolvable=truth['unsolvable'],expected=truth['expected'],answer=answer,status=status,
                    verified_solution=correct,justified_refusal=truth['unsolvable'] and answer is None and status in ('UNSOLVABLE','SKIPPED'),
                    integrity_passed=integrity,changed_files=changed,unexpected_files=unexpected,
                    candidate_data_route=routes.get(name),calls=len(events),
                    effective_cost=result.get('input_tokens',0)/10+result.get('output_tokens',0)+result.get('reasoning_tokens',0),
                    result=result)
                rows.append(row)
            arm_report=dict(experimental_joins=enabled,configuration=dict(budget=plan['budget_per_arm'] if live else 0,
                max_calls=plan['max_calls_per_arm'] if live else 0,concurrency=1,search_min_task_budget=config.search_min_task_budget,
                data_min_task_budget=config.data_min_task_budget,coding_min_task_budget=config.coding_min_task_budget),
                rows=rows,metrics=summarize(rows),groups={g:summarize([r for r in rows if r['group']==g]) for g in ('E41_core','E75_pilot')},
                by_type={t:summarize([r for r in rows if r['task_type']==t]) for t in ('math','search','data_analysis','coding')},
                actual_http_calls=requests,summary=summary)
            write(arm_dir/'report.json',arm_report)
            shutil.copytree(taskroot,arm_dir/'task_artifacts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            report['arms'][arm]=arm_report
            write(directory/'report.json',report)
            print(json.dumps(dict(arm=arm,metrics=arm_report['metrics'],groups=arm_report['groups'],calls=requests,cost=summary['effective_tokens_spent'])),flush=True)
            if summary['budget_state']['has_unaccounted_request'] or summary['budget_state']['remote_stopped']:
                report['status']='STOPPED_ACCOUNTING_OR_REMOTE'
                break
    if report['status']=='RUNNING':report['status']='COMPLETED' if len(report['arms'])==2 else 'INCOMPLETE'
    report['real_api_attempts']=sum(a['actual_http_calls'] for a in report['arms'].values()) if live else 0
    report['known_effective_tokens']=round(sum(a['summary']['effective_tokens_spent'] for a in report['arms'].values()),3)
    report['fixtures_unchanged']=hashes(TASK_FIXTURE/'tasks')==fixture['fixtures_sha256']
    report['prior_ledgers_unchanged']=all(digest(ROOT/p)==plan['frozen_hashes'][p] for p in plan['prior_unknown_ledgers'])
    if not live:
        candidate=report['arms']['candidate'];baseline=report['arms']['baseline']
        local=[r for r in candidate['rows'] if r['candidate_data_route'] in ('local','local_or')]
        report['offline_passed']=(report['status']=='COMPLETED' and report['real_api_attempts']==0
            and all(a['summary']['budget_state']['events']==[] for a in report['arms'].values())
            and len(local)==6 and all(r['verified_solution'] and r['calls']==0 for r in local)
            and all(r['integrity_passed'] for a in report['arms'].values() for r in a['rows'])
            and report['fixtures_unchanged'] and report['prior_ledgers_unchanged'])
    write(directory/'report.json',report)
    print(json.dumps({k:report[k] for k in ('status','real_api_attempts','known_effective_tokens','fixtures_unchanged','prior_ledgers_unchanged')}),flush=True)
    if not live:print('offline_passed:',report['offline_passed'],flush=True)
    print('Report:',directory/'report.json',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true')
    asyncio.run(run(p.parse_args().live))
