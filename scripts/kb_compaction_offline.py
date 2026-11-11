"""Audit compaction facts and actual reservation admission; no API/key access."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agents.search_solver import _parse_kb, solve_search_task
from harness.agents.kb_context import build_kb_context
from harness.agents.kb_compaction import table_context, PREFIX
from harness.config import TaskContext
from harness.planner.budget_tracker import BudgetTracker, BudgetDenied

class Capture:
    def __init__(self): self.payload = None
    async def complete(self, **payload):
        self.payload = payload
        return 'UNKNOWN', 0, 0, 0

async def main():
    rows = []
    cases = json.loads((ROOT/'experiments/E52_kb_compaction/cases.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as temp:
        for case in cases:
            root = Path(temp)/case['id']
            root.mkdir()
            for name, content in case['files'].items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            entities = _parse_kb(root/'kb')
            for arm, builder in (('plain', build_kb_context), ('table', table_context)):
                context = builder(case['question'], entities)
                capture = Capture()
                ctx = TaskContext(case['id'], 'search', case['question'], 1, root, root, case['task_budget'], False)
                with patch('harness.agents.search_solver.build_kb_context', builder):
                    await solve_search_task(ctx, capture)
                payload = capture.payload
                if payload is None: raise AssertionError('Fixture bypasses API path')
                estimate = len((payload['system_prompt']+payload['user_prompt']).encode('utf-8'))+1024
                grid = {}
                for budget in (200,250,300,400,600,900):
                    tracker = BudgetTracker(budget)
                    try:
                        _, cap = await tracker.reserve(case['id'], budget, estimate, payload['max_tokens'])
                        grid[budget] = dict(admitted=True, output_cap=cap)
                    except BudgetDenied:
                        grid[budget] = dict(admitted=False, output_cap=0)
                rows.append(dict(case=case['id'], arm=arm, context_bytes=len(context.text.encode('utf-8')),
                                 selected_names=context.names, complete_kb=context.complete_kb,
                                 table_encoded=context.text.startswith(PREFIX), input_reserve_estimate=estimate,
                                 task_budget=case['task_budget'], grid=grid, payload=payload))
    report = dict(scope='No API; captured prompts and actual BudgetTracker reservation grid',
                  api_calls=0, rows=rows, fixture_sha256=hashlib.sha256((ROOT/'experiments/E52_kb_compaction/cases.json').read_bytes()).hexdigest())
    path = ROOT/'experiments'/('E52_admission_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in rows:
        print(json.dumps({k:row[k] for k in ('case','arm','context_bytes','table_encoded','input_reserve_estimate','task_budget','grid')}, ensure_ascii=False))
    print('Report:', path)

if __name__ == '__main__': asyncio.run(main())
