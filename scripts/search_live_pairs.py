"""Paired live search check with a separately authorized ledger; no hidden retries."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
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
from harness.agents.search_solver import solve_search_task
from harness.workflow_runner import OpenJiuwenTaskRunner

FIXTURE = ROOT/'experiments'/'E50_search_live'
SOURCE_PATHS = ['harness/agents/search_solver.py', 'harness/agents/kb_context.py',
                'harness/agents/base_harness.py', 'harness/config.py', 'harness/workflow_runner.py',
                'harness/planner/budget_tracker.py', 'scripts/search_live_pairs.py']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

async def run(live=False):
    plan = json.loads((FIXTURE/'plan.json').read_text(encoding='utf-8'))
    for name, expected_hash in plan['frozen_hashes'].items():
        if digest(ROOT/name) != expected_hash:
            raise ValueError('Frozen input or source changed: '+name)
    legacy_path = ROOT/plan['legacy_ledger_path']
    if digest(legacy_path) != plan['legacy_ledger_sha256']:
        raise ValueError('Legacy ledger changed; inspect before proceeding')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/('E50_search_'+('live_' if live else 'preflight_')+stamp)
    if live:
        # A new invocation does not automatically reset or resume this experiment.
        with (FIXTURE/'live_started.json').open('x', encoding='utf-8') as f:
            json.dump(dict(directory=directory.name, started_at=stamp), f)
    directory.mkdir()
    settings = load_settings() if live else dict(LLM_BASE_URL='https://fixture.invalid/v1', LLM_API_KEY='fixture')
    spec = importlib.util.spec_from_file_location('e50_old_search', FIXTURE/'baseline_search_solver.py')
    old_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_module)
    cases = json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8'))
    tracker = BudgetTracker(plan['budget'], directory/'budget.json', max_requests=plan['max_calls'])
    rows = []
    recording_errors = []
    calls = 0
    original_transport = OpenJiuwenLLMBridge._get_transport
    report = dict(mode='LIVE' if live else 'PREFLIGHT_SYNTHETIC', scope=plan['scope'],
                  experiment_status='RUNNING', plan_sha256=digest(FIXTURE/'plan.json'),
                  source_hashes={name:digest(ROOT/name) for name in SOURCE_PATHS},
                  legacy_E46=dict(path=plan['legacy_ledger_path'], actual_cost=None,
                                 reserved_effective_tokens=343.1, ledger_unchanged=True),
                  rows=rows, recording_errors=recording_errors)
    def persist():
        report['budget'] = tracker.snapshot()
        report['attempted_transport_calls'] = calls
        report['real_api_calls'] = calls if live else 0
        report['real_known_effective_tokens'] = tracker.spent_effective_tokens if live else 0
        write_json(directory/'report.json', report)
    with tempfile.TemporaryDirectory(prefix='oj-live-search-') as tmp:
        config = HarnessConfig(Path(tmp), None, settings['LLM_BASE_URL'], settings['LLM_API_KEY'],
                               initial_budget_tokens=plan['budget'], max_concurrency=1,
                               request_timeout_sec=60, workflow_timeout_sec=180)
        runner = OpenJiuwenTaskRunner(config, tracker)
        def recording_transport(bridge):
            real_send = original_transport(bridge) if live else None
            async def send(payload):
                nonlocal calls
                calls += 1
                number = calls
                request_path = directory/f'request_{number:02d}.json'
                write_json(request_path, dict(task_id=bridge.task_id, payload=payload,
                                             mode=report['mode'], started_at=datetime.now(timezone.utc).isoformat()))
                if live:
                    data = await real_send(payload)
                else:
                    data = dict(usage=dict(prompt_tokens=0, completion_tokens=0),
                                choices=[dict(message=dict(content='UNSOLVABLE'), finish_reason='stop')])
                try:
                    write_json(directory/f'response_{number:02d}.json', dict(task_id=bridge.task_id, response=data))
                except OSError as exc:
                    recording_errors.append(dict(request=number, error=type(exc).__name__))
                return data
            return send
        persist()
        with patch.object(OpenJiuwenLLMBridge, '_get_transport', recording_transport):
            for index, case in enumerate(cases):
                if tracker.has_unaccounted_request or tracker.proxy_exhausted:
                    break
                arms = ['old', 'new'] if index % 2 == 0 else ['new', 'old']
                for position, arm in enumerate(arms):
                    if tracker.has_unaccounted_request or tracker.proxy_exhausted:
                        break
                    task_id = case['id']+'__'+arm
                    folder = Path(tmp)/task_id
                    folder.mkdir()
                    for filename, content in case['files'].items():
                        path = folder/filename
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(content, encoding='utf-8')
                    ctx = TaskContext(task_id, 'search', case['question'], 1, folder, folder,
                                      plan['per_task_budget'], False)
                    before_calls = calls
                    solver = old_module.solve_search_task if arm == 'old' else solve_search_task
                    with patch('harness.agents.base_harness.solve_search_task', solver):
                        result = await runner.run(ctx)
                    answer_file = folder/'answer.txt'
                    answer = answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
                    solved = case['expected'] is not None and result.status == 'SOLVED' and answer == case['expected']
                    refused = case['expected'] is None and answer is None and result.status == 'UNSOLVABLE'
                    row = dict(case=case['id'], arm=arm, order_in_pair=position, expected=case['expected'],
                               answer=answer, status=result.status, verified_solution=solved,
                               justified_refusal=refused, correct=solved or refused,
                               false_refusal=case['expected'] is not None and result.status=='UNSOLVABLE',
                               wrong_answer=answer is not None and not solved,
                               calls=calls-before_calls, effective_cost=result.effective_cost,
                               result=asdict(result), workflow=runner.runs[-1])
                    rows.append(row)
                    persist()
                    print(json.dumps({k:row[k] for k in ('case','arm','status','answer','correct','effective_cost','calls')}), flush=True)
    paired = [case['id'] for case in cases if {r['arm'] for r in rows if r['case']==case['id']}=={'old','new'}]
    def aggregate(arm, ids):
        subset = [r for r in rows if r['arm']==arm and r['case'] in ids]
        return dict(attempted=len(subset), verified_solutions=sum(r['verified_solution'] for r in subset),
                    justified_refusals=sum(r['justified_refusal'] for r in subset), correct=sum(r['correct'] for r in subset),
                    false_refusals=sum(r['false_refusal'] for r in subset), wrong_answers=sum(r['wrong_answer'] for r in subset),
                    known_effective_tokens=round(sum(r['effective_cost'] for r in subset), 3))
    report['metrics'] = dict(planned_pairs=len(cases), complete_pairs=len(paired),
                             arms={arm:aggregate(arm, paired) for arm in ('old','new')})
    report['experiment_status'] = 'STOPPED_UNKNOWN_COST' if tracker.has_unaccounted_request else (
        'COMPLETED' if len(rows)==2*len(cases) else 'INCOMPLETE')
    report['legacy_E46']['ledger_unchanged'] = digest(legacy_path)==plan['legacy_ledger_sha256']
    if not live:
        # Preflight verifies wiring, request caps and accounting, not answer quality.
        report['preflight_passed'] = (len(rows)==12 and calls==12 and not recording_errors
            and all(r['workflow']['state']=='COMPLETED' for r in rows)
            and all(json.loads(p.read_text(encoding='utf-8'))['payload']['max_tokens']==32
                    for p in directory.glob('request_*.json')))
    persist()
    print(json.dumps(dict(status=report['experiment_status'], metrics=report['metrics'],
                          real_api_calls=report['real_api_calls'],
                          real_known_effective_tokens=report['real_known_effective_tokens'],
                          preflight_passed=report.get('preflight_passed'))), flush=True)
    print('Report: '+str(directory/'report.json'), flush=True)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    asyncio.run(run(args.live))
