"""H04.35: preserve the math system contract and append only brevity guidance."""
import argparse,asyncio,json
from pathlib import Path
from unittest.mock import patch
import frozen_benchmark as bench
from harness.agents.base_harness import OpenJiuwenLLMBridge
TERSE_SUFFIX=' Keep code minimal: no comments, explanations, or unnecessary helper functions.'
BASELINE_MATH_PROMPT=(
    'Translate the math word problem into a short Python 3 script that computes and prints ONLY the final integer answer. '
    'If the problem is contradictory or impossible, print UNSOLVABLE. Output ONLY raw Python code without markdown.'
)
TERSE_MATH_PROMPT=BASELINE_MATH_PROMPT+TERSE_SUFFIX

def completion(original,math_ids):
    async def complete(bridge,model,system_prompt,user_prompt,max_tokens=512,temperature=0.0):
        if bridge.task_id in math_ids:
            if system_prompt!=BASELINE_MATH_PROMPT:raise ValueError('Baseline prompt changed')
            system_prompt+=TERSE_SUFFIX
        return await original(bridge,model,system_prompt,user_prompt,max_tokens=max_tokens,temperature=temperature)
    return complete
async def run(args):
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if plan['arm']=='baseline':return await bench.run(args)
    if plan['arm']!='compact':raise ValueError('Unknown arm')
    math_ids=set()
    for path in (bench.ROOT/plan['tasks']).glob('*/task.json'):
        public=json.loads(path.read_text(encoding='utf-8'))
        if public['task_type']=='math':math_ids.add(public['task_id'])
    with patch.object(OpenJiuwenLLMBridge,'complete',completion(OpenJiuwenLLMBridge.complete,math_ids)):
        return await bench.run(args)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
