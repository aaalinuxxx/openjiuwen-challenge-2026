"""Frozen score-first candidate comparison, no task-ID routing or golden answers."""
import argparse,asyncio,json
from unittest.mock import patch
from pathlib import Path
import frozen_benchmark as bench
from harness.agents.base_harness import OpenJiuwenLLMBridge,TruncatedGeneration
from harness.planner.budget_tracker import BudgetDenied
from terse_math_benchmark import BASELINE_MATH_PROMPT,TERSE_MATH_PROMPT
from numeric_recheck_policy import numeric_literal_only,CALCULATION_PROMPT

def candidate_completion(original,arm):
    async def complete(bridge,model,system_prompt,user_prompt,max_tokens=512,temperature=0.0):
        is_math=system_prompt==BASELINE_MATH_PROMPT
        prompt=TERSE_MATH_PROMPT if is_math and arm!='baseline' else system_prompt
        first=await original(bridge,model,prompt,user_prompt,max_tokens=max_tokens,temperature=temperature)
        if not is_math or arm!='terse_recheck' or not numeric_literal_only(first[0]):return first
        try:
            second=await original(bridge,model,CALCULATION_PROMPT,user_prompt,max_tokens=max_tokens,temperature=temperature)
        except (BudgetDenied,TruncatedGeneration):
            if bridge.tracker.has_unaccounted_request or bridge.tracker.proxy_exhausted:raise
            return first
        # A second numeric constant is not additional computational evidence.
        return first if numeric_literal_only(second[0]) else second
    return complete
async def run(args):
    plan=json.loads(args.plan.read_text(encoding='utf-8'));arm=plan['arm']
    if arm not in ('baseline','terse','terse_recheck'):raise ValueError(arm)
    with patch.object(OpenJiuwenLLMBridge,'complete',candidate_completion(OpenJiuwenLLMBridge.complete,arm)):
        return await bench.run(args)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True,type=Path);p.add_argument('--live',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
