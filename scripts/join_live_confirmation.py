"""One fresh API generation on the pre-frozen join multiplicity counterexample."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api_settings import load_settings
from multimodule_live import populate,write,digest
from csv_join_live import same_number
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.multi_csv import solve_multi_csv_task
from harness.workflow_runner import OpenJiuwenTaskRunner

FIXTURE=ROOT/'experiments/E64_join_confirmation'

async def run():
    plan=json.loads((FIXTURE/'live_plan.json').read_text(encoding='utf-8'))
    for name,sha in plan['frozen_hashes'].items():
        if digest(ROOT/name)!=sha: raise ValueError('Frozen source changed: '+name)
    baseline=json.loads((ROOT/plan['baseline_report']).read_text(encoding='utf-8'))
    if baseline['budget']['has_unaccounted_request']: raise ValueError('Unknown prior usage')
    if baseline['real_api_attempts']!=7 or baseline['known_effective_tokens']!=1211.4:
        raise ValueError('Unexpected cumulative ledger')
    case=json.loads((FIXTURE/'case.json').read_text(encoding='utf-8'))
    settings=load_settings()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/('E64_join_live_'+stamp)
    with (FIXTURE/'live_started.json').open('x',encoding='utf-8') as file:
        json.dump(dict(directory=directory.name,started_at=stamp),file)
    directory.mkdir()
    tracker=BudgetTracker(plan['budget'],directory/'budget.json',max_requests=1)
    original_transport=OpenJiuwenLLMBridge._get_transport
    count=0
    def recording_transport(bridge):
        transport=original_transport(bridge)
        async def send(payload):
            nonlocal count
            count+=1
            write(directory/'request.json',dict(task_id=bridge.task_id,payload=payload))
            response=await transport(payload)
            write(directory/'response.json',dict(task_id=bridge.task_id,response=response))
            return response
        return send
    write(directory/'report.json',dict(status='RUNNING',mode='LIVE',plan_sha256=digest(FIXTURE/'live_plan.json')))
    with tempfile.TemporaryDirectory(prefix='oj-join-confirmation-') as temp:
        root=Path(temp)
        populate(root,case['files'])
        config=HarnessConfig(root,None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],
            initial_budget_tokens=plan['budget'],max_concurrency=1,request_timeout_sec=60,workflow_timeout_sec=180)
        runner=OpenJiuwenTaskRunner(config,tracker)
        ctx=TaskContext(case['id'],'data_analysis',case['instruction'],2,root,root,1000,False)
        before={name:digest(root/name) for name in case['files']}
        with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording_transport),patch('harness.agents.base_harness.solve_data_task',solve_multi_csv_task):
            result=await runner.run(ctx)
        answer_file=root/'answer.txt'
        answer=answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
        unchanged=all((root/name).is_file() and digest(root/name)==sha for name,sha in before.items())
        solved=result.status=='SOLVED' and same_number(answer,case['expected']) and unchanged
        populate(directory/'inputs',case['files'])
        if answer is not None: (directory/'answer.txt').write_text(answer,encoding='utf-8')
    report=dict(mode='LIVE',status='STOPPED_UNKNOWN_COST' if tracker.has_unaccounted_request else 'COMPLETED',
        scope='One adaptively selected counterexample, unchanged candidate, no population-quality estimate',
        plan_sha256=digest(FIXTURE/'live_plan.json'),source_hashes=plan['frozen_hashes'],
        result=asdict(result),expected=case['expected'],answer=answer,solved=solved,
        wrong_answer=answer is not None and not solved,unchanged_inputs=unchanged,workflow=runner.runs[-1],
        real_api_attempts=count,known_effective_tokens=tracker.spent_effective_tokens,budget=tracker.snapshot(),
        cumulative_calls=7+count,cumulative_known_effective_tokens=round(1211.4+tracker.spent_effective_tokens,3))
    write(directory/'report.json',report)
    print(json.dumps({k:report[k] for k in ('status','expected','answer','solved','real_api_attempts','known_effective_tokens','cumulative_calls','cumulative_known_effective_tokens')}),flush=True)
    print('Report:',directory/'report.json',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.parse_args()
    asyncio.run(run())
