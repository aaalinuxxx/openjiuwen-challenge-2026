"""Actual SDK deadline controls with an async synthetic transport. No real HTTP."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge, solve_task
from harness.workflow_runner import OpenJiuwenTaskRunner
import harness.workflow_runner as workflow_module

CASES=[
    dict(name='fast',delay=.02,request=.8,workflow=1.2,post=0,status='SOLVED',unknown=False,known=12),
    dict(name='within_request_after_inherited_sdk',delay=1.5,request=2.0,workflow=3.0,post=0,status='SOLVED',unknown=False,known=12),
    dict(name='request_deadline',delay=.6,request=.1,workflow=1.2,post=0,status='ACCOUNTING_UNKNOWN',unknown=True,known=0,error='TimeoutError'),
    dict(name='external_workflow_cancellation',delay=.35,request=.8,workflow=1.2,post=0,forced_sdk=.15,status='WORKFLOW_FAILED',unknown=True,known=0,error='CancelledError'),
    dict(name='post_usage_processing',delay=.02,request=.1,workflow=3.0,post=1.5,status='SOLVED',unknown=False,known=12),
]

async def run(label):
    from openjiuwen.core.session.constants import WORKFLOW_EXECUTE_TIMEOUT
    directory=ROOT/'experiments'/(label+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    directory.mkdir(parents=True,exist_ok=False)
    rows=[]
    with patch.dict(os.environ,{'WORKFLOW_EXECUTE_TIMEOUT':'1.0'}):
        warmup=dict(name='warmup_not_scored',delay=.01,request=.8,workflow=1.2,post=0,forced_sdk=10,status='SOLVED',unknown=False,known=12)
        for case in [warmup]+CASES:
            with tempfile.TemporaryDirectory(prefix='oj-deadlines-') as temp:
                root=Path(temp)
                config=HarnessConfig(root,None,'https://fixture.invalid/v1','fixture-only',
                    initial_budget_tokens=1000,budget_audit_path=directory/(case['name']+'_budget.json'))
                # Old runner ignores these attributes. Candidate explicitly applies them.
                config.request_timeout_sec=case['request']
                config.workflow_timeout_sec=case['workflow']
                tracker=BudgetTracker(1000,config.budget_audit_path)
                runner=OpenJiuwenTaskRunner(config,tracker)
                ctx=TaskContext('main','other','Reply OK.',3,root,root,1000,False)
                actual_sdk=[]
                factory=runner.sdk.create_workflow_session
                def session_factory(*args,**kwargs):
                    envs=dict(kwargs.get('envs') or {})
                    if 'forced_sdk' in case: envs[WORKFLOW_EXECUTE_TIMEOUT]=case['forced_sdk']
                    actual_sdk.append(envs.get(WORKFLOW_EXECUTE_TIMEOUT,1.0))
                    kwargs['envs']=envs
                    return factory(*args,**kwargs)
                calls=[]
                async def transport(payload):
                    calls.append(payload['max_tokens'])
                    await asyncio.sleep(case['delay'])
                    return dict(usage=dict(prompt_tokens=20,completion_tokens=10),
                        choices=[dict(finish_reason='stop',message=dict(content='OK'))])
                async def delayed_solve(*args,**kwargs):
                    result=await solve_task(*args,**kwargs)
                    if case['post']: await asyncio.sleep(case['post'])
                    return result
                started=time.monotonic()
                with patch.object(runner.sdk,'create_workflow_session',session_factory), \
                     patch.object(OpenJiuwenLLMBridge,'_get_transport',lambda _:transport), \
                     patch.object(workflow_module,'solve_task',delayed_solve):
                    result=await runner.run(ctx)
                    elapsed=time.monotonic()-started
                    before_followup=len(calls)
                    followup=None
                    if tracker.has_unaccounted_request:
                        next_ctx=TaskContext('next','other','Reply OK.',3,root,root,1000,False)
                        followup=await solve_task(next_ctx,config,budget_tracker=tracker)
                        local_ctx=TaskContext('local','math',
                            'A warehouse starts with 10 boxes. It receives 2 boxes. How many boxes does it have at the end?',
                            3,root,root,1000,False)
                        local=await solve_task(local_ctx,config,budget_tracker=tracker)
                        local_answer=local.answer
                    else: local_answer=None
                snapshot=tracker.snapshot()
                error=snapshot['events'][0].get('error_type') if snapshot['events'] else None
                checks=dict(status=result.status==case['status'],
                    known=snapshot['known_effective_tokens']==case['known'],
                    unknown=snapshot['has_unaccounted_request']==case['unknown'],
                    exactly_one_transport=len(calls)==1,
                    no_followup_after_unknown=len(calls)==before_followup,
                    error=not case.get('error') or error==case['error'],
                    local_continues=not tracker.has_unaccounted_request or local_answer=='12')
                rows.append(dict(case=case['name'],desired=case,actual_sdk_timeout=actual_sdk,
                    status=result.status,answer=result.answer,elapsed_sec=round(elapsed,4),
                    calls=len(calls),checks=checks,passed=all(checks.values()),
                    followup_status=followup.status if followup else None,local_answer=local_answer,
                    budget=snapshot,workflow_runs=runner.runs))
    warmup_row=rows.pop(0)
    if not warmup_row['passed']: raise AssertionError('SDK warmup failed; measurements invalid')
    sources=[ROOT/'harness/workflow_runner.py',ROOT/'harness/agents/base_harness.py',ROOT/'harness/config.py',Path(__file__).resolve()]
    report=dict(scope='real openJiuwen 0.1.19 with scaled deadlines after explicit warmup and synthetic transport; not API latency',
        api_calls=0,real_effective_tokens=0,warmup=warmup_row,total=len(rows),passed=sum(r['passed'] for r in rows),rows=rows,
        source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(total=report['total'],passed=report['passed'],
        failures={r['case']:[k for k,v in r['checks'].items() if not v] for r in rows if not r['passed']},api_calls=0)))
    print('Report:',directory/'report.json')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);a=p.parse_args()
    if not a.label.replace('_','').isalnum(): p.error('Invalid label')
    asyncio.run(run(a.label))
