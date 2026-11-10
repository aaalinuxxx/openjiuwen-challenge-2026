"""Actual openJiuwen integration controls. No live API or credentials used.

Public fixtures measure local delivery; synthetic HTTP controls only accounting,
workflow execution and failure semantics, never LLM quality or real token cost.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import HarnessConfig
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.planner.scheduler import TaskScheduler
from harness.workflow_runner import load_sdk


def write_task(root, name, kind='other', instruction='Return OK.'):
    directory = root / name
    directory.mkdir()
    (directory/'task.json').write_text(json.dumps(dict(
        task_id=name, task_type=kind, instruction=instruction, reward=1)), encoding='utf-8')
    return directory


def validate_trace(summary):
    traces = summary['workflow_runs']
    assert summary['execution_engine'] == 'openjiuwen'
    assert len({t['session_id'] for t in traces}) == len(traces)
    assert len({t['workflow_id'] for t in traces}) == len(traces)
    assert all(t['state'] == 'COMPLETED' and t['stages'] == ['solve', 'finalize'] for t in traces), traces


async def run():
    load_sdk()  # Fail explicitly if real SDK cannot load; never substitute a fake.
    rows = []
    source = ROOT.parent/'task-dir'/'task-dir'
    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in source.rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='oj-sdk-controls-') as tmp:
        base = Path(tmp)
        samples = base/'samples'
        samples.mkdir()
        truths = {}
        for task in source.glob('*/task.json'):
            data = json.loads(task.read_text(encoding='utf-8'))
            truths[task.parent.name] = data
            target = samples/task.parent.name
            shutil.copytree(task.parent, target)
            (target/'task.json').write_text(json.dumps({k: v for k, v in data.items()
                if k not in ('expected', 'unsolvable')}), encoding='utf-8')
            for answer in target.rglob('answer.txt'):
                answer.unlink()

        async def forbidden(payload):
            raise AssertionError('HTTP must not be reached at zero budget')

        config = HarnessConfig(samples, None, 'https://fixture.invalid/v1', 'fixture-only', initial_budget_tokens=0)
        with patch.object(OpenJiuwenLLMBridge, '_get_transport', lambda self: forbidden):
            summary = await TaskScheduler(config).run_all()
        answers = {}
        for name, truth in truths.items():
            answer_file = samples/name/'answer.txt'
            answer = answer_file.read_text(encoding='utf-8').strip() if answer_file.exists() else None
            answers[name] = dict(answer=answer,
                correct=truth['task_type'] != 'coding' and answer == str(truth['expected']), reward=truth['reward'])
        validate_trace(summary)
        assert len(truths) == 8 and summary['solved_count'] == 6
        assert sum(a['correct'] for a in answers.values()) == 6
        assert sum(a['reward'] for a in answers.values() if a['correct']) == 16
        assert not summary['budget_state']['events']
        rows.append(dict(case='public_zero_budget', summary=summary, answers=answers))

        for case, count, budget, concurrency in [
            ('parallel', 5, 300, 5), ('bad_content', 1, 1000, 1),
            ('unknown_cost', 2, 1000, 1), ('coding_delivery', 1, 2000, 1),
            ('finalize_failure', 1, 1000, 1),
        ]:
            directory = base/case
            directory.mkdir()
            for i in range(count):
                target = write_task(directory, f'remote_{i}',
                    'coding' if case == 'coding_delivery' else 'other')
                if case == 'coding_delivery':
                    (target/'calc.py').write_text('def add(a, b):\n    return a - b\n', encoding='utf-8')
                    (target/'test_calc.py').write_text(
                        'import unittest\nfrom calc import add\nclass Tests(unittest.TestCase):\n'
                        '    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n'
                        '        self.assertEqual(add(-2, 1), -1)\n'
                        'if __name__ == "__main__": unittest.main()\n', encoding='utf-8')
            if case == 'unknown_cost':
                write_task(directory, 'local', 'math',
                    'A warehouse starts with 10 boxes. It receives 2 boxes. How many boxes does it have at the end?')
            tests_before = {p: p.read_bytes() for p in directory.rglob('test_*.py')}
            calls = []

            async def synthetic(payload):
                cap = payload['max_tokens']
                calls.append(dict(model=payload['model'], output_cap=cap))
                await asyncio.sleep(0.01)
                if case == 'unknown_cost':
                    raise OSError('Synthetic transport failure')
                if case == 'bad_content':
                    return dict(usage=dict(prompt_tokens=20, completion_tokens=10))
                return dict(usage=dict(prompt_tokens=0, completion_tokens=min(120, cap)),
                    choices=[dict(message=dict(content='def add(a, b):\n    return a + b\n'
                        if case == 'coding_delivery' else 'OK'))])

            config = HarnessConfig(directory, None, 'https://fixture.invalid/v1', 'fixture-only',
                initial_budget_tokens=budget, max_concurrency=concurrency)
            with patch.object(OpenJiuwenLLMBridge, '_get_transport', lambda self: synthetic):
                scheduler = TaskScheduler(config)
                if case == 'finalize_failure':
                    with patch('harness.workflow_runner.finalize', side_effect=OSError('Synthetic write failure')):
                        summary = await scheduler.run_all()
                else:
                    summary = await scheduler.run_all()
            if case != 'finalize_failure':
                validate_trace(summary)
            actual_answers = {p.parent.name: p.read_text(encoding='utf-8').strip()
                              for p in directory.glob('*/answer.txt')}
            assert all(p.read_bytes() == content for p, content in tests_before.items())
            if case == 'parallel':
                assert len(calls) == 2 and summary['effective_tokens_spent'] == 182
                assert summary['effective_tokens_spent'] <= budget
                assert summary['solved_count'] == 2
            elif case == 'bad_content':
                assert len(calls) == 1 and summary['effective_tokens_spent'] == 12
                assert not actual_answers and not summary['budget_state']['has_unaccounted_request']
            elif case == 'unknown_cost':
                assert len(calls) == 1 and summary['budget_state']['has_unaccounted_request']
                assert actual_answers == {'local': '12'}
            elif case == 'coding_delivery':
                assert len(calls) == 1 and actual_answers == {'remote_0': 'DONE'}
                assert 'return a + b' in (directory/'remote_0'/'calc.py').read_text(encoding='utf-8')
            else:
                assert len(calls) == 1 and summary['effective_tokens_spent'] == 120
                assert not actual_answers and summary['solved_count'] == 0
                assert summary['workflow_runs'][0]['state'] == 'FAILED'
                assert summary['workflow_runs'][0]['stages'] == ['solve', 'finalize']
            rows.append(dict(case=case, summary=summary, synthetic_http_calls=calls, answers=actual_answers))

    assert all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in originals.items())
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    report = dict(scope='real openJiuwen SDK; synthetic HTTP only; no live model-quality measurements',
        sdk_version=version('openjiuwen'), python_version=sys.version, api_calls=0, rows=rows,
        source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in list((ROOT/'harness').rglob('*.py')) + [Path(__file__)]})
    path = ROOT/'experiments'/f'E28_sdk_workflow_{stamp}.json'
    with path.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(dict(sdk_version=report['sdk_version'], controls_passed=len(rows), api_calls=0,
        public_correct=6, public_total=8, public_score=16, public_max_score=20)))
    print('Report:', path)


if __name__ == '__main__':
    asyncio.run(run())
