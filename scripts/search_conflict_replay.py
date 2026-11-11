"""Replay captured real conflict responses through current SDK; no network/key."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.kb_context import build_kb_context
from harness.agents.kb_compaction import table_context
from harness.workflow_runner import OpenJiuwenTaskRunner

async def main():
    plan=json.loads((ROOT/'experiments/E54b_replay_plan.json').read_text(encoding='utf-8'))
    case=next(c for c in json.loads((ROOT/'experiments/E52_kb_compaction/cases.json').read_text(encoding='utf-8')) if c['id']=='conflicting_city')
    rows=[]
    for item in plan['sources']:
        source=ROOT/item['path']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']: raise ValueError('Captured response changed')
        captured=json.loads(source.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(prefix='oj-conflict-replay-') as temp:
            root=Path(temp)
            for name,content in case['files'].items():
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding='utf-8')
            tracker=BudgetTracker(900,max_requests=1)
            config=HarnessConfig(root,None,'https://fixture.invalid/v1','offline-fixture',initial_budget_tokens=900)
            runner=OpenJiuwenTaskRunner(config,tracker)
            ctx=TaskContext('replay','search',case['question'],1,root,root,900,False)
            async def transport(payload): return captured['response']
            with patch.object(OpenJiuwenLLMBridge,'_get_transport',return_value=transport), patch(
                    'harness.agents.search_solver.build_kb_context',build_kb_context if item['arm']=='plain' else table_context):
                result=await runner.run(ctx)
            saved=(root/'answer.txt').exists()
            passed=result.status=='UNKNOWN' and not saved and not tracker.has_unaccounted_request
            rows.append(dict(source=item['path'],source_sha256=item['sha256'],
                original_response=captured['response']['choices'][0]['message']['content'],
                result=asdict(result),answer_file_exists=saved,passed=passed,
                replayed_historical_budget=tracker.snapshot(),workflow=runner.runs))
    report=dict(scope='Captured live-response replay with synthetic transport; NOT new live generations',
        real_api_calls=0,real_effective_tokens=0,passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        solver_sha256=hashlib.sha256((ROOT/'harness/agents/search_solver.py').read_bytes()).hexdigest())
    path=ROOT/'experiments'/('E54b_response_replay_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('real_api_calls','passed','total')}))
    print('Report:',path)
    if report['passed']!=report['total']: raise AssertionError('Replay failed')

if __name__=='__main__': asyncio.run(main())
