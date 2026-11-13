"""H04.34: only the math system prompt changes; no extra calls or budget."""
import argparse,asyncio,json
from pathlib import Path
from unittest.mock import patch
import frozen_benchmark as bench
from harness.agents.base_harness import OpenJiuwenLLMBridge
COMPACT_MATH_PROMPT=(
    "Return concise executable Python 3 only. Print the final integer, or UNSOLVABLE if contradictory/impossible. "
    "No comments, Markdown, explanations or file writes. Avoid unnecessary functions; prefer built-ins and short expressions."
)
def completion(original,math_ids):
    async def complete(bridge,model,system_prompt,user_prompt,max_tokens=512,temperature=0.0):
        if bridge.task_id in math_ids:system_prompt=COMPACT_MATH_PROMPT
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
