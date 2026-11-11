"""Capture actual solver prompts with fixed synthetic responses; no HTTP."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import TaskContext
from harness.agents.search_solver import solve_search_task

async def run(label):
    fixture=ROOT/'experiments'/'E47_search_context'/'cases.json'
    cases=json.loads(fixture.read_text(encoding='utf-8'))
    rows=[]
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='oj-kb-context-') as tmp:
            root=Path(tmp);kb=root/'kb';kb.mkdir()
            for name,content in case['files'].items():
                (kb/name).write_text(content,encoding='utf-8')
            captured=[]
            class Bridge:
                async def complete(self,**kwargs):
                    captured.append(kwargs)
                    return case['reply'],0,0,0
            ctx=TaskContext(case['name'],'search',case['question'],3,root,root,2000,False)
            result=await solve_search_task(ctx,Bridge())
            prompt=captured[0]['user_prompt'] if captured else ''
            context=prompt.split('KB Records:\n',1)[-1].split('\n\nQuestion:',1)[0] if prompt else ''
            checks=case['checks'];fail=[]
            if result.status != checks.get('expected_status',result.status): fail.append('status')
            if result.answer != checks.get('expected_answer',result.answer): fail.append('answer')
            if len(captured)!=checks.get('expected_calls',len(captured)): fail.append('calls')
            for value in checks.get('required_values',[]):
                if value not in context: fail.append('missing:'+value)
            for value in checks.get('forbidden_values',[]):
                if value in context: fail.append('decoy:'+value)
            records=sum(line.startswith('# ') for line in context.splitlines())
            if records>checks.get('max_records',10**9): fail.append('record_cap')
            if len(context.encode('utf-8'))>checks.get('max_context_bytes',10**9): fail.append('byte_cap')
            rows.append(dict(case=case['name'],passed=not fail,failed_checks=fail,status=result.status,
                answer=result.answer,synthetic_calls=len(captured),context_records=records,
                context_bytes=len(context.encode('utf-8')),captured_requests=captured))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    report=dict(label=label,api_calls=0,scope='structural prompt/control evaluation with fixed synthetic refusal; not model accuracy',
        fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        solver_sha256=hashlib.sha256((ROOT/'harness/agents/search_solver.py').read_bytes()).hexdigest(),
        total=len(rows),passed=sum(r['passed'] for r in rows),rows=rows)
    path=ROOT/'experiments'/f'{label}_{stamp}.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(total=report['total'],passed=report['passed'],
        failures={r['case']:r['failed_checks'] for r in rows if not r['passed']},api_calls=0)))
    print('Report:',path)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);args=p.parse_args()
    if not args.label.replace('_','').isalnum(): p.error('Invalid label')
    asyncio.run(run(args.label))
