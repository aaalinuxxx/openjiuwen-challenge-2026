"""Exercise the real entrypoint with real SDK and zero API budget on copies."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT.parent/'task-dir'/'task-dir'
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='oj-cli-controls-') as tmp:
        directory = Path(tmp)/'tasks'
        directory.mkdir()
        truths = {}
        for task in source.glob('*/task.json'):
            truth = json.loads(task.read_text(encoding='utf-8'))
            truths[task.parent.name] = truth
            target = directory/task.parent.name
            shutil.copytree(task.parent, target)
            (target/'task.json').write_text(json.dumps({k: v for k, v in truth.items()
                if k not in ('expected', 'unsolvable')}), encoding='utf-8')
            for answer in target.rglob('answer.txt'):
                answer.unlink()
        env = os.environ.copy()
        env.update(LLM_BASE_URL='https://fixture.invalid/v1', LLM_API_KEY='fixture-only',
                   BUDGET='999', TOKEN_BUDGET='888', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.run([sys.executable, str(ROOT/'run_agent.py'), '--tasks-dir', str(directory),
            '--budget', '0'], cwd=ROOT, env=env, capture_output=True, encoding='utf-8', timeout=180)
        assert process.returncode == 0, (process.stdout, process.stderr)
        audit_line = next(line for line in process.stdout.splitlines() if 'Budget audit: ' in line)
        audit_path = Path(audit_line.split('Budget audit: ', 1)[1].split('; unaccounted request:', 1)[0])
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        assert not audit['events'], audit
        rows = []
        for name, truth in truths.items():
            path = directory/name/'answer.txt'
            answer = path.read_text(encoding='utf-8').strip() if path.exists() else None
            correct = truth['task_type'] != 'coding' and answer == str(truth['expected'])
            rows.append(dict(task_id=name, answer=answer, correct=correct, reward=truth['reward']))
        assert len(rows) == 8 and sum(r['correct'] for r in rows) == 6
        assert sum(r['reward'] for r in rows if r['correct']) == 16
        assert all(not r['answer'] for r in rows if r['task_id'].startswith('coding_'))
    assert all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items())
    report = dict(scope='real run_agent CLI; actual SDK; cleaned public fixtures; explicit budget 0 overrides env 999/888',
        python=sys.version, returncode=process.returncode, api_calls=0, budget_state=audit, rows=rows,
        stdout=process.stdout, stderr=process.stderr,
        source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [Path(__file__), ROOT/'run_agent.py', ROOT/'harness'/'workflow_runner.py']})
    path = ROOT/'experiments'/('E29_sdk_cli_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    with path.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(correct=6, total=8, score=16, max_score=20, api_calls=0, cli_returncode=0)))
    print('Report:', path)


if __name__ == '__main__':
    main()
