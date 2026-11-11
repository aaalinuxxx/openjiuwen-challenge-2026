"""Explicit offline/live scheduler benchmark. Inputs are always temporary copies."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import HarnessConfig
from harness.planner.scheduler import TaskScheduler
from harness.agents.base_harness import OpenJiuwenLLMBridge
from api_settings import load_settings, DEFAULT_CONFIG


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}



def verify_coding(target, protected, answer):
    """DONE is a delivery marker; correctness comes from the original tests."""
    if answer != 'DONE' or not protected:
        return False
    for rel, original in protected.items():
        test = target/rel
        if not test.exists() or test.read_bytes() != original:
            return False
        try:
            completed = subprocess.run([sys.executable, '-B', test.name], cwd=test.parent,
                                       capture_output=True, timeout=8)
        except subprocess.TimeoutExpired:
            return False
        if completed.returncode != 0:
            return False
    return all((target/rel).exists() and (target/rel).read_bytes() == original
               for rel, original in protected.items())

async def run(args):
    source = args.tasks_dir.resolve()
    originals = sorted(source.glob('*/task.json'))
    if not originals:
        raise ValueError('Task directory is missing or contains no tasks')
    initial = hashes(source)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/f'{args.label}_{stamp}'
    directory.mkdir(parents=True, exist_ok=False)
    settings = load_settings(args.config) if args.live else dict(
        LLM_BASE_URL='https://fixture.invalid/v1', LLM_API_KEY='offline-fixture')
    with tempfile.TemporaryDirectory(prefix='oj-reviewed-benchmark-') as temp:
        task_root = Path(temp)/'tasks'
        task_root.mkdir()
        truths, protected = {}, {}
        for task in originals:
            truth = json.loads(task.read_text(encoding='utf-8'))
            if 'expected' not in truth or 'unsolvable' not in truth:
                # Public originals can omit unsolvable; an explicit expected answer is mandatory.
                if 'expected' not in truth:
                    raise ValueError('Expected answer is required for benchmark evaluation')
                truth['unsolvable'] = False
            truths[task.parent.name] = truth
            target = task_root/task.parent.name
            shutil.copytree(task.parent, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (target/'task.json').write_text(json.dumps({k:v for k,v in truth.items()
                if k not in ('expected', 'unsolvable')}), encoding='utf-8')
            for answer in target.rglob('answer.txt'):
                answer.unlink()
            protected[task.parent.name] = {p.relative_to(target):p.read_bytes()
                for p in target.rglob('test_*.py')}
        config = HarnessConfig(task_root, None, settings['LLM_BASE_URL'], settings['LLM_API_KEY'],
            initial_budget_tokens=args.budget if args.live else 0, max_concurrency=args.concurrency,
            execution_engine=args.engine, max_api_calls=args.max_calls if args.live else 0,
            budget_audit_path=directory/'budget.json')
        config.search_min_task_budget = args.search_min_budget
        config.data_min_task_budget = args.data_min_budget
        scheduler = TaskScheduler(config)
        if args.live:
            response_dir = directory/'http_responses'
            response_dir.mkdir()
            original_get_transport = OpenJiuwenLLMBridge._get_transport
            def recording_transport(bridge):
                transport = original_get_transport(bridge)
                async def send(payload):
                    data = await transport(payload)
                    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
                    audit = dict(task_id=bridge.task_id, model=payload['model'],
                        output_cap=payload['max_tokens'], response=data)
                    try:
                        (response_dir/(name+'.json')).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
                    except OSError:
                        pass  # Recording failure must not prevent the bridge from settling usage.
                    return data
                return send
            with patch.object(OpenJiuwenLLMBridge, '_get_transport', recording_transport):
                summary = await scheduler.run_all()
        else:
            with patch.object(OpenJiuwenLLMBridge, '_get_transport',
                              side_effect=AssertionError('Offline transport forbidden')):
                summary = await scheduler.run_all()
        rows = []
        for name, truth in truths.items():
            target = task_root/name
            answer_file = target/'answer.txt'
            answer = answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
            result = summary['task_results'].get(truth['task_id'], {})
            status = result.get('status', 'SKIPPED' if truth['task_id'] in summary['skipped_tasks'] else 'NOT_RUN')
            unsolvable = truth['unsolvable']
            verified = not unsolvable and answer is not None and answer == str(truth['expected']).strip()
            if truth['task_type'] == 'coding':
                verified = not unsolvable and verify_coding(target, protected[name], answer)
            justified_refusal = unsolvable and answer is None and status in ('UNSOLVABLE', 'SKIPPED')
            rows.append(dict(task_id=truth['task_id'], task_type=truth['task_type'], status=status,
                notes=result.get('notes', summary['skipped_tasks'].get(truth['task_id'], '')),
                expected=truth['expected'], answer=answer, unsolvable=unsolvable, reward=truth['reward'],
                verified_solution=verified, justified_refusal=justified_refusal,
                mere_abstention=unsolvable and answer is None and not justified_refusal))
        shutil.copytree(task_root, directory/'task_artifacts',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if hashes(source) != initial:
        raise AssertionError('Original task data changed')
    metrics = dict(total=len(rows), verified_solutions=sum(r['verified_solution'] for r in rows),
        justified_refusals=sum(r['justified_refusal'] for r in rows),
        mere_abstentions=sum(r['mere_abstention'] for r in rows),
        wrong_submitted_answers=sum(r['answer'] is not None and not r['verified_solution'] for r in rows),
        earned_score=sum(r['reward'] for r in rows if r['verified_solution']),
        max_solvable_score=sum(r['reward'] for r in rows if not r['unsolvable']),
        calls=len([e for e in summary['budget_state']['events'] if e['status'] != 'NOT_SENT']),
        known_effective_tokens=summary['effective_tokens_spent'],
        has_unaccounted_request=summary['budget_state']['has_unaccounted_request'])
    if not args.live and (metrics['calls'] or metrics['known_effective_tokens']):
        raise AssertionError('Offline invariant violated')
    report = dict(mode='LIVE' if args.live else 'OFFLINE',
        scope='known dev or public examples; not independent holdout',
        input_hashes=initial, source_hashes=hashes(ROOT/'harness'),
        benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        configuration=dict(budget=args.budget, max_calls=args.max_calls,
            search_min_budget=args.search_min_budget, data_min_budget=args.data_min_budget),
        metrics=metrics, summary=summary, rows=rows)
    output = directory/'report.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metrics, ensure_ascii=False))
    print('Report:', output)
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks-dir', type=Path, default=ROOT.parent/'task-dir'/'task-dir')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--budget', type=float, default=0)
    parser.add_argument('--max-calls', type=int, default=4)
    parser.add_argument('--search-min-budget', type=float, default=0)
    parser.add_argument('--data-min-budget', type=float, default=0)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--engine', choices=['openjiuwen', 'direct'], default='openjiuwen')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--label', default='E34_scheduler_recheck')
    args = parser.parse_args(argv)
    if any(not math.isfinite(v) or not 0 <= v <= 1000 for v in (args.search_min_budget, args.data_min_budget)):
        parser.error('Per-domain minimum budget must be finite and between 0 and 1000')
    if not args.label.replace('_', '').isalnum():
        parser.error('Invalid report label')
    if not math.isfinite(args.budget) or not 0 <= args.budget <= 3000:
        parser.error('Budget must be finite and between 0 and 3000')
    if not args.live and args.budget != 0:
        parser.error('Positive budget requires --live')
    if args.live and args.budget <= 0:
        parser.error('--live requires a positive explicit --budget')
    if not 1 <= args.max_calls <= 12 or not 1 <= args.concurrency <= 5:
        parser.error('Invalid call/concurrency limit')
    return args


if __name__ == '__main__':
    asyncio.run(run(parse_args()))
