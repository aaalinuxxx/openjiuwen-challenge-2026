"""E57/E58: bounded live validation of one-module repairs with dependencies."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api_settings import load_settings
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.workflow_runner import OpenJiuwenTaskRunner

FIXTURE = ROOT / 'experiments/E57_multimodule'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def populate(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_text(content, encoding='utf-8')

def check(root, files, extra=None):
    outputs = []
    for name in sorted(n for n in files if n.startswith('test_') and n.endswith('.py')):
        p = subprocess.run([sys.executable, '-B', name], cwd=root, capture_output=True, text=True, timeout=10)
        outputs.append(dict(name=name, code=p.returncode, stdout=p.stdout, stderr=p.stderr))
    if extra is not None:
        p = subprocess.run([sys.executable, '-B', '-c', extra], cwd=root, capture_output=True, text=True, timeout=10)
        outputs.append(dict(name='additional_checks', code=p.returncode, stdout=p.stdout, stderr=p.stderr))
    return dict(passed=all(x['code']==0 for x in outputs), checks=outputs)

def validate(cases):
    rows = []
    with tempfile.TemporaryDirectory(prefix='oj-oracles-') as temp:
        for case in cases:
            root = Path(temp) / case['id']
            populate(root, case['files'])
            before = check(root, case['files'], case['checks'])
            (root / case['target']).write_text(case['reference'], encoding='utf-8')
            after = check(root, case['files'], case['checks'])
            rows.append(dict(case=case['id'], original=before, reference=after))
    report = dict(api_calls=0, passed=all(not r['original']['passed'] and r['reference']['passed'] for r in rows), rows=rows)
    write(FIXTURE/'oracle_validation.json', report)
    if not report['passed']:
        raise ValueError('Fixture oracle validation failed')
    print('Oracle validation: 6/6 original failures and reference passes', flush=True)

async def run(live):
    plan = json.loads((FIXTURE/'live_plan.json').read_text(encoding='utf-8'))
    for name, sha in plan['frozen_hashes'].items():
        if digest(ROOT/name) != sha:
            raise ValueError('Frozen source changed: '+name)
    cases = json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8'))
    settings = load_settings() if live else dict(LLM_BASE_URL='https://fixture.invalid/v1', LLM_API_KEY='offline')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/('E58_multimodule_'+('live_' if live else 'preflight_')+stamp)
    if live:
        with (FIXTURE/'live_started.json').open('x', encoding='utf-8') as file:
            json.dump(dict(directory=directory.name, started_at=stamp), file)
    directory.mkdir()
    tracker = BudgetTracker(plan['budget'], directory/'budget.json', max_requests=plan['max_calls'])
    original_transport = OpenJiuwenLLMBridge._get_transport
    count = 0
    rows, recording_errors = [], []
    report = dict(mode='LIVE' if live else 'PREFLIGHT_REFERENCE_PATCHES', status='RUNNING',
                  plan_sha256=digest(FIXTURE/'live_plan.json'), source_hashes=plan['frozen_hashes'],
                  scope=plan['scope'], rows=rows, recording_errors=recording_errors)
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
                case = next(c for c in cases if c['id']==bridge.task_id)
                data = dict(usage=dict(prompt_tokens=0,completion_tokens=0),
                            choices=[dict(message=dict(content=case['reference']),finish_reason='stop')])
            try:
                write(directory/f'response_{index:02d}.json', dict(task_id=bridge.task_id,response=data))
            except OSError as error:
                recording_errors.append(dict(request=index,error_type=type(error).__name__))
            return data
        return send
    persist()
    with tempfile.TemporaryDirectory(prefix='oj-multimodule-') as temp:
        config = HarnessConfig(Path(temp), None, settings['LLM_BASE_URL'], settings['LLM_API_KEY'],
                               initial_budget_tokens=plan['budget'], max_concurrency=1,
                               request_timeout_sec=60, workflow_timeout_sec=180)
        runner = OpenJiuwenTaskRunner(config, tracker)
        with patch.object(OpenJiuwenLLMBridge, '_get_transport', recording_transport):
            for case in cases:
                if tracker.has_unaccounted_request or tracker.proxy_exhausted:
                    break
                root = Path(temp)/case['id']
                populate(root, case['files'])
                initial_hashes = {name:digest(root/name) for name in case['files']}
                ctx = TaskContext(case['id'],'coding',case['instruction'],2,root,root,plan['per_task_budget'],False)
                before = count
                result = await runner.run(ctx)
                answer_file = root/'answer.txt'
                answer = answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
                checks = check(root, case['files'], case['checks'])
                unchanged = all(digest(root/n)==h for n,h in initial_hashes.items() if n!=case['target'])
                added = sorted(p.name for p in root.iterdir() if p.name not in case['files'] and p.name!='answer.txt')
                delivered = result.status=='SOLVED' and answer=='DONE'
                solved = delivered and checks['passed'] and unchanged and not added
                control = case['support']=='ambiguous_control'
                row = dict(case=case['id'],support=case['support'],status=result.status,answer=answer,
                           solved=solved,wrong_delivery=delivered and not solved,
                           boundary_control_passed=control and result.status=='UNKNOWN' and count==before and answer is None,
                           unchanged_non_target=unchanged,unexpected_files=added,
                           original_hashes=initial_hashes,final_hashes={n:digest(root/n) for n in case['files']},
                           validation=checks,calls=count-before,effective_cost=result.effective_cost,
                           result=asdict(result),workflow=runner.runs[-1])
                artifact = directory/case['id']
                artifact.mkdir()
                populate(artifact/'original',case['files'])
                for name in case['files']:
                    destination=artifact/'final'/name
                    destination.parent.mkdir(exist_ok=True)
                    shutil.copyfile(root/name,destination)
                if answer_file.exists():
                    shutil.copyfile(answer_file,artifact/'final'/'answer.txt')
                write(artifact/'validation.json',row)
                rows.append(row)
                persist()
                print(json.dumps({k:row[k] for k in ('case','status','solved','calls','effective_cost','unchanged_non_target')},ensure_ascii=False),flush=True)
    report['metrics'] = dict(planned=6,attempted=len(rows),
        explicit_solved=sum(r['solved'] for r in rows if r['support']=='explicit'),explicit_total=4,
        solvable_solved=sum(r['solved'] for r in rows if r['support']!='ambiguous_control'),solvable_total=5,
        wrong_deliveries=sum(r['wrong_delivery'] for r in rows),
        boundary_controls_passed=sum(r['boundary_control_passed'] for r in rows),
        calls=sum(r['calls'] for r in rows))
    report['prior_ledgers_unchanged'] = all(digest(ROOT/p)==plan['frozen_hashes'][p] for p in plan['prior_unknown_ledgers'])
    report['status'] = 'STOPPED_UNKNOWN_COST' if tracker.has_unaccounted_request else ('COMPLETED' if len(rows)==6 else 'INCOMPLETE')
    if not live:
        report['preflight_passed'] = (len(rows)==6 and count==4 and not recording_errors
            and report['metrics']['explicit_solved']==4 and report['metrics']['boundary_controls_passed']==1
            and all(r['unchanged_non_target'] for r in rows)
            and all(r['status']=='UNKNOWN' for r in rows if r['support']=='paraphrase'))
    persist()
    print(json.dumps({k:report[k] for k in ('status','metrics','real_api_attempts','known_effective_tokens','prior_ledgers_unchanged')},ensure_ascii=False),flush=True)
    if not live:
        print('preflight_passed:',report['preflight_passed'],flush=True)
    print('Report:',directory/'report.json',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--validate',action='store_true')
    args=parser.parse_args()
    if args.validate:
        validate(json.loads((FIXTURE/'cases.json').read_text(encoding='utf-8')))
    else:
        asyncio.run(run(args.live))
