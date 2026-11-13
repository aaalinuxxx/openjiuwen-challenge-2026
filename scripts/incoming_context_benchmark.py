"""Matched incoming-context arms; original production path for candidate."""
import argparse,asyncio,json
from pathlib import Path
from unittest.mock import patch
import frozen_benchmark as bench
from harness.agents.kb_context import build_kb_context

def forward_only(question,entities,**kwargs):
    kwargs['include_incoming']=False
    return build_kb_context(question,entities,**kwargs)
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true');args=p.parse_args()
plan=json.loads(args.plan.read_text(encoding='utf-8'))
if plan['context_arm']=='forward':
    with patch('harness.agents.search_solver.build_kb_context',forward_only):
        code=asyncio.run(bench.run(args))
elif plan['context_arm']=='incoming':code=asyncio.run(bench.run(args))
else:raise ValueError('Unknown context arm')
raise SystemExit(code)
