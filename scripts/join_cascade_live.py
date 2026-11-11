"""E67/E68: real JSON-to-Python cascade versus direct generated Python."""
import argparse
import asyncio
import csv
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api_settings import load_settings
from multimodule_live import populate,write,digest
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.data_solver import solve_data_task
from harness.agents.multi_csv import solve_multi_csv_task,select_csv_inputs
from harness.agents.join_plans import solve_join_plan_task
from harness.agents.join_cascade import solve_join_cascade_task
from harness.workflow_runner import OpenJiuwenTaskRunner

FIXTURE=ROOT/'experiments/E67_join_cascade'

def same_number(answer,expected):
    if answer is None or expected is None: return False
    try:
        value=Decimal(answer)
        return value.is_finite() and value==Decimal(expected)
    except InvalidOperation:
        return False

def validate(cases):
    rows=[]
    for case in cases:
        if case['sql'] is None:
            with tempfile.TemporaryDirectory() as temp:
                populate(Path(temp),case['files'])
                rejected=select_csv_inputs(Path(temp),case['instruction']) is None
            rows.append(dict(case=case['id'],boundary_control=True,selection_rejected=rejected,passed=rejected))
            continue
        with sqlite3.connect(':memory:') as connection:
            for name,content in case['files'].items():
                reader=csv.reader(io.StringIO(content))
                columns=next(reader)
                table=Path(name).stem
                schema=', '.join('"'+c+'" TEXT' for c in columns)
                connection.execute('CREATE TABLE "'+table+'" ('+schema+')')
                placeholders=','.join('?' for c in columns)
                connection.executemany('INSERT INTO "'+table+'" VALUES ('+placeholders+')',list(reader))
            answer=str(connection.execute(case['sql']).fetchone()[0])
        rows.append(dict(case=case['id'],expected=case['expected'],oracle=answer,passed=same_number(answer,case['expected'])))
    report=dict(api_calls=0,passed=all(r['passed'] for r in rows),rows=rows,
                scope='Independent SQLite calculation with TEXT join keys; not model-generated code')
    write(FIXTURE/'oracle_validation.json',report)
    if not report['passed']: raise ValueError('Oracle mismatch')
    print('Independent SQLite oracle validation: 5/5',flush=True)

async def run(live):
    plan=json.loads((FIXTURE/'live_plan.json').read_text(encoding='utf-8'))
    for name,sha in plan['frozen_hashes'].items():
        if digest(ROOT/name)!=sha: raise ValueError('Frozen source changed: '+name)
    cases=json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8'))
    settings=load_settings() if live else dict(LLM_BASE_URL='https://fixture.invalid/v1',LLM_API_KEY='offline')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/('E68_join_cascade_'+('live_' if live else 'preflight_')+stamp)
    if live:
        with (FIXTURE/'live_started.json').open('x',encoding='utf-8') as file:
            json.dump(dict(directory=directory.name,started_at=stamp),file)
    directory.mkdir()
    tracker=BudgetTracker(plan['budget'],directory/'budget.json',max_requests=plan['max_calls'])
    original_transport=OpenJiuwenLLMBridge._get_transport
    count=0
    rows,recording_errors=[],[]
    traces={}
    report=dict(mode='LIVE' if live else 'PREFLIGHT_GOLD_PLANS_AND_ANSWERS',status='RUNNING',scope=plan['scope'],
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
            phase='json_plan' if payload['messages'][0]['content'].startswith('Return ONLY a JSON join plan') else 'python'
            traces.setdefault(bridge.task_id,[]).append(phase)
            write(directory/f'request_{index:02d}.json',dict(task_id=bridge.task_id,stage=phase,payload=payload,mode=report['mode']))
            if live:
                data=await transport(payload)
            else:
                case=next(c for c in cases if c['id']==bridge.task_id.split('__')[0])
                if phase=='json_plan':
                    content=json.dumps(case['gold_plan']) if case['gold_plan'] is not None else 'UNSUPPORTED'
                else:
                    content='print('+repr(case['expected'])+')'
                data=dict(usage=dict(prompt_tokens=0,completion_tokens=0),
                          choices=[dict(message=dict(content=content),finish_reason='stop')])
            try:
                write(directory/f'response_{index:02d}.json',dict(task_id=bridge.task_id,response=data))
            except OSError as error:
                recording_errors.append(dict(request=index,error_type=type(error).__name__))
            return data
        return send
    persist()
    with tempfile.TemporaryDirectory(prefix='oj-csv-pairs-') as temp:
        config=HarnessConfig(Path(temp),None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],
                             initial_budget_tokens=plan['budget'],max_concurrency=1,request_timeout_sec=60,workflow_timeout_sec=180)
        runner=OpenJiuwenTaskRunner(config,tracker)
        with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording_transport):
            for i,case in enumerate(cases):
                for order,arm in enumerate(['python','cascade'] if i%2==0 else ['cascade','python']):
                    if tracker.has_unaccounted_request or tracker.proxy_exhausted: break
                    task_id=case['id']+'__'+arm
                    root=Path(temp)/task_id
                    populate(root,case['files'])
                    initial={name:digest(root/name) for name in case['files']}
                    ctx=TaskContext(task_id,'data_analysis',case['instruction'],2,root,root,plan['per_task_budget'],False)
                    before=count
                    with patch('harness.agents.base_harness.solve_data_task',solve_multi_csv_task if arm=='python' else solve_join_cascade_task):
                        result=await runner.run(ctx)
                    answer_file=root/'answer.txt'
                    answer=answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
                    unchanged=all((root/n).is_file() and digest(root/n)==h for n,h in initial.items())
                    added=sorted(p.name for p in root.iterdir() if p.name not in case['files'] and p.name!='answer.txt')
                    solved=result.status=='SOLVED' and same_number(answer,case['expected']) and unchanged and not added
                    control=case['gold_plan'] is None and arm=='cascade' and result.status=='UNKNOWN' and answer is None and unchanged
                    row=dict(case=case['id'],arm=arm,order_in_pair=order,expected=case['expected'],status=result.status,
                             answer=answer,solved=solved,unsupported_abstention=control,supported=case['gold_plan'] is not None,
                             wrong_answer=answer is not None and not solved,unchanged_inputs=unchanged,
                             unexpected_files=added,original_hashes=initial,
                             calls=count-before,stages=traces.get(task_id,[]),effective_cost=result.effective_cost,result=asdict(result),workflow=runner.runs[-1])
                    artifact=directory/task_id
                    artifact.mkdir()
                    populate(artifact/'original',case['files'])
                    (artifact/'final').mkdir()
                    for name in case['files']:
                        if (root/name).is_file(): shutil.copyfile(root/name,artifact/'final'/name)
                    if answer_file.exists(): shutil.copyfile(answer_file,artifact/'final'/'answer.txt')
                    write(artifact/'validation.json',row)
                    rows.append(row)
                    persist()
                    print(json.dumps({k:row[k] for k in ('case','arm','status','answer','solved','calls','effective_cost')},ensure_ascii=False),flush=True)
                if tracker.has_unaccounted_request or tracker.proxy_exhausted: break
    metrics={}
    for arm in ('python','cascade'):
        subset=[r for r in rows if r['arm']==arm]
        metrics[arm]=dict(attempted=len(subset),solved=sum(r['solved'] for r in subset),solvable_total=5,
                         supported_solved=sum(r['solved'] for r in subset if r['supported']),supported_total=2,
                         outside_plan_solved=sum(r['solved'] for r in subset if not r['supported']),outside_plan_total=3,
                         fallback_tasks=sum(r['stages']==['json_plan','python'] for r in subset),
                         wrong_answers=sum(r['wrong_answer'] for r in subset),
                         calls=sum(r['calls'] for r in subset),effective_tokens=round(sum(r['effective_cost'] for r in subset),3))
    report['metrics']=metrics
    report['prior_ledgers_unchanged']=all(digest(ROOT/p)==plan['frozen_hashes'][p] for p in plan['prior_unknown_ledgers'])
    report['status']='STOPPED_UNKNOWN_COST' if tracker.has_unaccounted_request else ('COMPLETED' if len(rows)==10 else 'INCOMPLETE')
    if not live:
        report['preflight_passed']=(len(rows)==10 and count==13 and not recording_errors
            and metrics['python']['solved']==5 and metrics['cascade']['solved']==5
            and metrics['cascade']['fallback_tasks']==3 and all(r['unchanged_inputs'] for r in rows))
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
