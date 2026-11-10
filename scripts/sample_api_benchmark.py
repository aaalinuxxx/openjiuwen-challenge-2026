"""Sequential diagnostic of public examples, not the final openJiuwen harness.

No external packages. Noreason only, no retries, original inputs kept intact.
"""
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
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import TaskContext
from harness.agents.coding_solver import solve_coding_task
from harness.agents.math_solver import solve_math_task
from harness.agents.data_solver import solve_data_task
from harness.agents.search_solver import solve_search_task
from probe_neuraldeep import NoRedirect


def write_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class Bridge:
    def __init__(self, settings, budget, report_path, report, *, max_calls=4):
        self.settings, self.budget = settings, budget
        self.report_path, self.report = report_path, report
        self.spent, self.blocked, self.calls = 0.0, False, 0
        self.task_id = None
        if type(max_calls) is not int or not 1 <= max_calls <= 12:
            raise ValueError('Diagnostic call limit must be between 1 and 12')
        self.max_calls = max_calls

    @staticmethod
    def request_reserve(system_prompt, user_prompt, max_tokens):
        # Heuristic, not a provider-certified token bound.
        return (len((system_prompt + user_prompt).encode('utf-8')) + 1024) / 10 + max_tokens

    async def complete(self, model, system_prompt, user_prompt, max_tokens=512, temperature=0):
        if model not in ('qwen3.8-27b-noreason', 'qwen3.6-35b-a3b-noreason'):
            raise RuntimeError('Reasoning models are disabled in this diagnostic')
        # Conservative heuristic, not a provider-certified input-token bound.
        reserve = self.request_reserve(system_prompt, user_prompt, max_tokens)
        if self.blocked or self.calls >= self.max_calls or self.spent + reserve > self.budget:
            raise RuntimeError('Local request gate closed')
        payload = dict(model=model, messages=[dict(role='system', content=system_prompt),
            dict(role='user', content=user_prompt)], max_tokens=max_tokens, temperature=temperature)
        event = dict(task_id=self.task_id, model=model, output_cap=max_tokens,
                     reserved_effective_tokens=reserve, status='STARTED')
        self.report['requests'].append(event)
        self.calls += 1
        write_json(self.report_path, self.report)
        started = time.monotonic()
        request = urllib.request.Request(self.settings['LLM_BASE_URL']+'/chat/completions',
            data=json.dumps(payload).encode(), headers={'Content-Type':'application/json',
            'Authorization':'Bearer '+self.settings['LLM_API_KEY']})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
                data = json.load(response)
            usage = data.get('usage')
            if not isinstance(usage, dict):
                raise ValueError('Missing usage')
            inp, out = usage['prompt_tokens'], usage['completion_tokens']
            reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens', 0)
            if any(type(v) is not int or v < 0 for v in (inp, out, reasoning)):
                raise ValueError('Invalid usage')
            if reasoning or usage.get('reasoning_tokens', 0):
                raise ValueError('Unexpected reasoning usage; billing contract needs inspection')
            cost = inp/10 + out
            self.spent += cost
            event.update(status='ACCOUNTED', prompt_tokens=inp, completion_tokens=out,
                         reasoning_tokens=0, effective_cost=cost)
            self.report['effective_tokens'] = self.spent
            if cost > reserve:
                self.blocked = True
                event['reserve_exceeded'] = True
            # Cost is persisted before attempting to interpret model output.
            write_json(self.report_path, self.report)
            content = data['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError('Invalid content')
            return content, inp, out, 0
        except Exception as exc:
            self.blocked = True
            event['error_type'] = type(exc).__name__
            if event['status'] == 'STARTED':
                event['status'] = 'COST_UNKNOWN_STOPPED'
                self.report['has_unaccounted_request'] = True
            raise RuntimeError('API diagnostic stopped; see request event') from None
        finally:
            event['elapsed_sec'] = round(time.monotonic()-started, 3)
            write_json(self.report_path, self.report)


async def run(args):
    settings = {}
    for line in args.config.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line:
            k,v = line.split('=',1)
            settings[k.strip()] = v.strip().strip('\"').strip("'")
    settings['LLM_BASE_URL'] = settings.get('LLM_BASE_URL','').rstrip('/')
    if settings['LLM_BASE_URL'] != 'https://api.neuraldeep.ru/v1' or not settings.get('LLM_API_KEY','').startswith('sk-'):
        raise ValueError('Check API configuration; values are not logged')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    run_dir = ROOT / 'experiments' / ('E03_samples_' + stamp)
    run_dir.mkdir(parents=True)
    report_path = run_dir / 'report.json'
    report = dict(scope='public samples; direct solvers; no scheduler or openJiuwen integration',
        local_budget=args.budget, requests=[], tasks=[], effective_tokens=0,
        has_unaccounted_request=False, source_hashes={str(p.relative_to(ROOT)):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'harness').rglob('*.py')})
    bridge = Bridge(settings, args.budget, report_path, report)
    originals = sorted(args.tasks_dir.glob('*/task.json'),
                       key=lambda p: (p.parent.name.startswith('coding'), p.parent.name))
    if len(originals) != 8:
        raise ValueError('This diagnostic expects the eight public examples')
    for source in originals:
        truth = json.loads(source.read_text(encoding='utf-8'))
        target = run_dir / 'tasks' / source.parent.name
        shutil.copytree(source.parent, target)
        meta = {k:v for k,v in truth.items() if k not in ('expected','unsolvable')}
        write_json(target/'task.json', meta)
        for answer in target.rglob('answer.txt'):
            answer.unlink()
        workspace = target/'workspace' if (target/'workspace').exists() else target
        protected = {p: p.read_bytes() for p in workspace.glob('test_*.py')}
        ctx = TaskContext(task_id=meta['task_id'], task_type=meta['task_type'],
            instruction=meta['instruction'], reward=meta['reward'], task_dir=target,
            workspace_dir=workspace, max_token_budget=max(0,args.budget-bridge.spent),
            allow_reasoning_escalation=False)
        bridge.task_id = ctx.task_id
        row = dict(task_id=ctx.task_id, reward=ctx.reward, correct=False)
        cost_before = bridge.spent
        try:
            solver = {'coding':solve_coding_task,'math':solve_math_task,
                      'search':solve_search_task,'data_analysis':solve_data_task}[ctx.task_type]
            result = await solver(ctx, bridge)
            row['status'] = result.status
            if result.status == 'SOLVED' and result.answer is not None:
                (target/'answer.txt').write_text(str(result.answer).strip()+'\n', encoding='utf-8')
                if ctx.task_type == 'coding':
                    row['correct'] = bool(protected) and result.answer.strip()=='DONE'
                    for test, original in protected.items():
                        if not test.exists() or test.read_bytes()!=original:
                            row['correct'] = False
                            break
                        proc = subprocess.run([sys.executable,test.name],cwd=workspace,
                                              capture_output=True,timeout=8)
                        row['correct'] = row['correct'] and proc.returncode==0
                else:
                    row['correct'] = str(result.answer).strip()==str(truth['expected']).strip()
        except Exception as exc:
            row.update(status='ERROR_OR_LOCAL_STOP', error_type=type(exc).__name__)
        row['effective_cost'] = round(bridge.spent-cost_before,3)
        report['tasks'].append(row)
        write_json(report_path, report)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    report['summary'] = dict(correct=sum(t['correct'] for t in report['tasks']), total=8,
        score=sum(t['reward'] for t in report['tasks'] if t['correct']),max_score=20,
        effective_tokens=round(bridge.spent,3), calls=bridge.calls,
        has_unaccounted_request=report['has_unaccounted_request'])
    write_json(report_path, report)
    print(json.dumps(report['summary'],ensure_ascii=False))
    print('Report:',report_path)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=ROOT.parent/'neuraldeep.txt')
    parser.add_argument('--tasks-dir',type=Path,default=ROOT.parent/'task-dir'/'task-dir')
    parser.add_argument('--budget',type=float,default=3000)
    args=parser.parse_args()
    if not math.isfinite(args.budget) or not 0<=args.budget<=3000:
        parser.error('Diagnostic budget must be between 0 and 3000')
    asyncio.run(run(args))
