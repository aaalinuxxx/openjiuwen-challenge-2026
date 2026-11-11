"""One explicitly authorized E54 real-API regression, no retries."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api_settings import load_settings
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.agents.kb_compaction import table_context
from harness.workflow_runner import OpenJiuwenTaskRunner

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

async def main():
    plan=json.loads((ROOT/'experiments/E54_conflict_live_plan.json').read_text(encoding='utf-8'))
    for path,sha in plan['frozen_hashes'].items():
        if digest(ROOT/path)!=sha: raise ValueError('Frozen source changed')
    settings=load_settings()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/('E54_conflict_live_'+stamp)
    with (ROOT/'experiments/E54_live_started.json').open('x',encoding='utf-8') as file:
        json.dump(dict(directory=directory.name),file)
    directory.mkdir()
    tracker=BudgetTracker(600,directory/'budget.json',max_requests=1)
    case=next(c for c in json.loads((ROOT/'experiments/E52_kb_compaction/cases.json').read_text(encoding='utf-8')) if c['id']=='conflicting_city')
    calls=0
    recording_errors=[]
    original=OpenJiuwenLLMBridge._get_transport
    def capture(bridge):
        send=original(bridge)
        async def transport(payload):
            nonlocal calls
            calls+=1
            write(directory/'request.json',dict(task_id=bridge.task_id,payload=payload))
            data=await send(payload)
            try: write(directory/'response.json',dict(task_id=bridge.task_id,response=data))
            except OSError as error: recording_errors.append(type(error).__name__)
            return data
        return transport
    with tempfile.TemporaryDirectory(prefix='oj-conflict-followup-') as temp:
        root=Path(temp)
        for name,content in case['files'].items():
            path=root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8')
        config=HarnessConfig(root,None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],initial_budget_tokens=600)
        ctx=TaskContext('conflicting_city_followup','search',case['question'],1,root,root,600,False)
        runner=OpenJiuwenTaskRunner(config,tracker)
        with patch.object(OpenJiuwenLLMBridge,'_get_transport',capture), patch('harness.agents.search_solver.build_kb_context',table_context):
            result=await runner.run(ctx)
        answer_exists=(root/'answer.txt').exists()
    report=dict(scope='Single known dev failure follow-up; not independent generalization or repeated paired test',
                result=asdict(result),answer_file_exists=answer_exists,real_api_attempts=calls,
                known_effective_tokens=tracker.spent_effective_tokens,budget=tracker.snapshot(),
                wrong_answer_prevented=not answer_exists and result.status in ('UNKNOWN','UNSOLVABLE'),
                justified_refusal=result.status=='UNSOLVABLE',workflow=runner.runs,
                recording_errors=recording_errors,source_hashes=plan['frozen_hashes'])
    write(directory/'report.json',report)
    print(json.dumps({k:report[k] for k in ('result','real_api_attempts','known_effective_tokens','wrong_answer_prevented','justified_refusal')},ensure_ascii=False),flush=True)
    print('Report:',directory/'report.json',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.parse_args()
    asyncio.run(main())
