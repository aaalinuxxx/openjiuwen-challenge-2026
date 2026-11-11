"""E53 paired real-API validation of E52 lossless KB serialization."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api_settings import load_settings
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.kb_context import build_kb_context
from harness.agents.kb_compaction import table_context
from harness.workflow_runner import OpenJiuwenTaskRunner

FIXTURE = ROOT/'experiments/E52_kb_compaction'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

async def run(live):
    plan = json.loads((FIXTURE/'live_plan.json').read_text(encoding='utf-8'))
    for name, sha in plan['frozen_hashes'].items():
        if digest(ROOT/name) != sha: raise ValueError('Frozen source changed: '+name)
    cases = json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8'))
    settings = load_settings() if live else dict(LLM_BASE_URL='https://fixture.invalid/v1', LLM_API_KEY='offline')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/('E53_compaction_'+('live_' if live else 'preflight_')+stamp)
    if live:
        with (FIXTURE/'live_started.json').open('x', encoding='utf-8') as file:
            json.dump(dict(directory=directory.name, started_at=stamp), file)
    directory.mkdir()
    tracker = BudgetTracker(plan['budget'], directory/'budget.json', max_requests=plan['max_calls'])
    rows, recording_errors = [], []
    count = 0
    original_transport = OpenJiuwenLLMBridge._get_transport
    report = dict(mode='LIVE' if live else 'PREFLIGHT_SYNTHETIC', status='RUNNING',
                  scope=plan['scope'], plan_sha256=digest(FIXTURE/'live_plan.json'),
                  rows=rows, recording_errors=recording_errors, source_hashes=plan['frozen_hashes'])
    def persist():
        report['budget'] = tracker.snapshot()
        report['real_api_attempts'] = count if live else 0
        report['known_effective_tokens'] = tracker.spent_effective_tokens if live else 0
        write(directory/'report.json', report)
    def recording_transport(bridge):
        transport = original_transport(bridge) if live else None
        async def send(payload):
            nonlocal count
            count += 1
            index = count
            write(directory/f'request_{index:02d}.json', dict(task_id=bridge.task_id, payload=payload, mode=report['mode']))
            if live:
                data = await transport(payload)
            else:
                data = dict(usage=dict(prompt_tokens=0,completion_tokens=0),
                            choices=[dict(message=dict(content='UNKNOWN'),finish_reason='stop')])
            try:
                write(directory/f'response_{index:02d}.json', dict(task_id=bridge.task_id,response=data))
            except OSError as error:
                recording_errors.append(dict(request=index,error_type=type(error).__name__))
            return data
        return send
    persist()
    with tempfile.TemporaryDirectory(prefix='oj-compaction-') as temp:
        config = HarnessConfig(Path(temp), None, settings['LLM_BASE_URL'], settings['LLM_API_KEY'],
                               initial_budget_tokens=plan['budget'], max_concurrency=1,
                               request_timeout_sec=60, workflow_timeout_sec=180)
        runner = OpenJiuwenTaskRunner(config, tracker)
        with patch.object(OpenJiuwenLLMBridge, '_get_transport', recording_transport):
            for i, case in enumerate(cases):
                arms = ['plain','table'] if i%2==0 else ['table','plain']
                for position, arm in enumerate(arms):
                    if tracker.has_unaccounted_request or tracker.proxy_exhausted: break
                    task_id = case['id']+'__'+arm
                    root = Path(temp)/task_id
                    root.mkdir()
                    for filename, content in case['files'].items():
                        path = root/filename
                        path.parent.mkdir(parents=True,exist_ok=True)
                        path.write_text(content,encoding='utf-8')
                    ctx = TaskContext(task_id,'search',case['question'],1,root,root,case['task_budget'],False)
                    before = count
                    builder = build_kb_context if arm=='plain' else table_context
                    with patch('harness.agents.search_solver.build_kb_context',builder):
                        result = await runner.run(ctx)
                    answer_file = root/'answer.txt'
                    answer = answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
                    solved = case['expected'] is not None and result.status=='SOLVED' and answer==case['expected']
                    refused = case['expected'] is None and result.status=='UNSOLVABLE' and answer is None
                    row = dict(case=case['id'],arm=arm,order_in_pair=position,task_budget=case['task_budget'],
                               expected=case['expected'],status=result.status,answer=answer,
                               solved=solved,justified_refusal=refused,correct=solved or refused,
                               false_refusal=case['expected'] is not None and result.status=='UNSOLVABLE',
                               wrong_answer=answer is not None and not solved,calls=count-before,
                               effective_cost=result.effective_cost,result=asdict(result),workflow=runner.runs[-1])
                    rows.append(row)
                    persist()
                    print(json.dumps({k:row[k] for k in ('case','arm','status','answer','correct','calls','effective_cost')},ensure_ascii=False),flush=True)
                if tracker.has_unaccounted_request or tracker.proxy_exhausted: break
    complete = [c['id'] for c in cases if len([r for r in rows if r['case']==c['id']])==2]
    submitted = [name for name in complete if all(r['calls']==1 for r in rows if r['case']==name)]
    def summarize(arm, ids):
        subset = [r for r in rows if r['arm']==arm and r['case'] in ids]
        return dict(attempted=len(subset),solved=sum(r['solved'] for r in subset),
                    justified_refusals=sum(r['justified_refusal'] for r in subset),
                    correct=sum(r['correct'] for r in subset),wrong_answers=sum(r['wrong_answer'] for r in subset),
                    false_refusals=sum(r['false_refusal'] for r in subset),
                    calls=sum(r['calls'] for r in subset),
                    known_effective_tokens=round(sum(r['effective_cost'] for r in subset),3))
    report['metrics'] = dict(planned_pairs=len(cases),complete_pairs=len(complete),
                             arms={a:summarize(a,complete) for a in ('plain','table')},
                             paired_submitted_ids=submitted,
                             paired_submitted={a:summarize(a,submitted) for a in ('plain','table')})
    report['prior_ledgers_unchanged'] = all(digest(ROOT/p)==plan['frozen_hashes'][p] for p in plan['prior_unknown_ledgers'])
    report['status'] = 'STOPPED_UNKNOWN_COST' if tracker.has_unaccounted_request else (
        'COMPLETED' if len(rows)==2*len(cases) else 'INCOMPLETE')
    if not live:
        report['preflight_passed'] = (len(rows)==12 and count==11 and not recording_errors
            and all(r['workflow']['state']=='COMPLETED' for r in rows)
            and all(json.loads(p.read_text(encoding='utf-8'))['payload']['max_tokens']==32 for p in directory.glob('request_*.json')))
    persist()
    print(json.dumps({k:report[k] for k in ('status','metrics','real_api_attempts','known_effective_tokens','prior_ledgers_unchanged')},ensure_ascii=False),flush=True)
    if not live: print('preflight_passed:',report['preflight_passed'],flush=True)
    print('Report:',directory/'report.json',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    asyncio.run(run(parser.parse_args().live))
