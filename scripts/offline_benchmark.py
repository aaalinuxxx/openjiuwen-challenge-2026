"""Network-free diagnostic benchmark; not a full competition evaluation."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import TaskContext
from harness.planner.feature_extractor import extract_task_features
from harness.planner.unsolvable_filter import check_unsolvable_zero_token
from harness.agents.math_solver import solve_math_task
from harness.agents.data_solver import solve_data_task
from harness.agents.search_solver import solve_search_task


class NeedsAPI(Exception):
    pass


class OfflineBridge:
    async def complete(self, **kwargs):
        raise NeedsAPI()


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def evaluate_samples(source):
    rows = []
    with tempfile.TemporaryDirectory(prefix='oj-benchmark-') as tmp:
        for original in sorted(source.glob('*/task.json')):
            truth = json.loads(original.read_text(encoding='utf-8'))
            task_dir = Path(tmp) / original.parent.name
            shutil.copytree(original.parent, task_dir)
            public = {k: v for k, v in truth.items() if k not in ('expected', 'unsolvable')}
            (task_dir / 'task.json').write_text(json.dumps(public), encoding='utf-8')
            for answer in task_dir.rglob('answer.txt'):
                answer.unlink()
            meta, features = extract_task_features(task_dir)
            skip, reason = check_unsolvable_zero_token(meta['instruction'], features)
            row = dict(task_id=meta['task_id'], reward=meta['reward'], correct=False,
                       status='SKIPPED' if skip else 'PENDING', reason=reason)
            workspace = task_dir / 'workspace' if (task_dir / 'workspace').exists() else task_dir
            if not skip:
                if meta['task_type'] == 'coding':
                    # No repair performed offline; only measure the original code.
                    tests = sorted(workspace.glob('test_*.py'))
                    passed = bool(tests)
                    for test in tests:
                        try:
                            result = subprocess.run([sys.executable, test.name], cwd=workspace,
                                                    capture_output=True, timeout=8)
                            passed = passed and result.returncode == 0
                        except subprocess.TimeoutExpired:
                            passed = False
                    row.update(status='ALREADY_PASSES' if passed else 'NEEDS_REPAIR', correct=passed)
                else:
                    ctx = TaskContext(task_id=meta['task_id'], task_type=meta['task_type'],
                                      instruction=meta['instruction'], reward=meta['reward'],
                                      task_dir=task_dir, workspace_dir=workspace,
                                      max_token_budget=0, allow_reasoning_escalation=False,
                                      features=features)
                    solver = {'math': solve_math_task, 'data_analysis': solve_data_task,
                              'search': solve_search_task}[ctx.task_type]
                    try:
                        result = await solver(ctx, OfflineBridge())
                        row.update(status=result.status, answer=result.answer,
                                   correct=result.status == 'SOLVED' and
                                   str(result.answer).strip() == str(truth['expected']).strip())
                    except NeedsAPI:
                        row['status'] = 'NEEDS_API'
                    except Exception as exc:
                        row.update(status='ERROR', error=type(exc).__name__)
            rows.append(row)
    return rows


def evaluate_filter():
    """Small independent counterexamples; labels describe semantic solvability."""
    rows = []
    with tempfile.TemporaryDirectory(prefix='oj-filter-') as tmp:
        def case(name, kind, instruction, files, solvable, simulate_timeout=False):
            folder = Path(tmp) / name
            folder.mkdir()
            (folder / 'task.json').write_text(json.dumps(dict(task_id=name, task_type=kind,
                instruction=instruction, reward=1)), encoding='utf-8')
            for rel, content in files.items():
                dest = folder / 'workspace' / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding='utf-8')
            if simulate_timeout:
                with patch('harness.planner.feature_extractor.subprocess.run',
                           side_effect=subprocess.TimeoutExpired('test', 5)):
                    meta, feat = extract_task_features(folder)
            else:
                meta, feat = extract_task_features(folder)
            skip, reason = check_unsolvable_zero_token(instruction, feat)
            rows.append(dict(task_id=name, solvable=solvable, skipped=skip, reason=reason,
                             false_skip=solvable and skip, simulated_timeout=simulate_timeout))
        csv_question = "How many units of product 'widget' were sold in months 1 through 2 inclusive?"
        case('empty_sum', 'data_analysis', csv_question,
             {'sales.csv': 'order_id,region,product,month,units,price\n'}, True)
        test = '''import unittest
class T(unittest.TestCase):
    def test_values(self):
        x = 1
        self.assertEqual(x, 1)
        x = 2
        self.assertEqual(x, 2)
if __name__ == '__main__': unittest.main()
'''
        case('changing_state', 'coding', 'Fix mylib.py; do not edit tests.',
             {'test_mylib.py': test, 'mylib.py': '# no repair needed\n'}, True)
        case('repairable_timeout', 'coding', 'Fix the infinite loop in mylib.py.',
             {'test_mylib.py': 'import mylib\nassert mylib.total([1,2]) == 3\n',
              'mylib.py': 'def total(xs):\n    while True: pass\n'}, True, True)
        case('capitalized_instruction', 'search', 'Please Answer: In which year was Irina Smith born?',
             {'kb/irina.md': '# Irina Smith\nBorn: 1983\n'}, True)
        case('division_zero', 'math', 'A warehouse starts with 12 boxes. Then the stock is split equally into 0 warehouses and it keeps one share (rounded down).', {}, False)
        case('missing_csv', 'data_analysis', csv_question, {}, False)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks-dir', type=Path, default=ROOT.parent / 'task-dir' / 'task-dir')
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('label must be alphanumeric')
    if not args.tasks_dir.is_dir() or not any(args.tasks_dir.glob("*/task.json")):
        parser.error("Task directory is missing or contains no tasks")
    sources = sorted((ROOT / 'harness').rglob('*.py'))
    inputs = sorted(p for p in args.tasks_dir.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    before = {str(p.relative_to(args.tasks_dir)): fingerprint(p) for p in inputs}
    started = time.monotonic()
    samples = asyncio.run(evaluate_samples(args.tasks_dir))
    filters = evaluate_filter()
    assert all(fingerprint(p) == before[str(p.relative_to(args.tasks_dir))] for p in inputs)
    report = dict(label=args.label, scope='offline diagnostics; no scheduler/API/Docker evaluation',
                  api_calls=0, effective_tokens=0, python=sys.version,
                  elapsed_sec=round(time.monotonic()-started, 3),
                  source_hashes={str(p.relative_to(ROOT)): fingerprint(p) for p in sources},
                  input_hashes=before, original_inputs_unchanged=True,
                  samples=samples, filter_cases=filters,
                  summary=dict(correct_samples=sum(r['correct'] for r in samples),
                      sample_total=len(samples), diagnostic_score=sum(r['reward'] for r in samples if r['correct']),
                      max_sample_score=sum(r['reward'] for r in samples),
                      false_skips=sum(r['false_skip'] for r in filters),
                      solvable_filter_cases=sum(r['solvable'] for r in filters)))
    out = ROOT / 'experiments' / (args.label + '.json')
    out.parent.mkdir(exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report['summary'], ensure_ascii=False))
    print(out)


if __name__ == '__main__':
    main()
