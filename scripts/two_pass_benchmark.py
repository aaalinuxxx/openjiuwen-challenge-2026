"""H04.32: short first attempts, then one guarded retry; experimental only."""
import argparse, asyncio, json
from contextvars import ContextVar
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import frozen_benchmark as bench
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.planner.scheduler import TaskScheduler
from harness.planner.budget_tracker import BudgetTracker

ACTIVE = ContextVar('two_pass_active', default=None)

class RetryTracker(BudgetTracker):
    def allocate_task_budget(self, *args, **kwargs):
        allocation = super().allocate_task_budget(*args, **kwargs)
        state = ACTIVE.get()
        if state and state['pass'] == 2:
            # Ledger limits are cumulative: add already paid usage, never reset it.
            inp, out, reason = self.usage_for_task(state['task_id'])
            allocation += inp / 10 + out + reason
        return allocation

def scheduler_type(caps):
    class TwoPassScheduler(TaskScheduler):
        def __init__(self, config):
            if config.max_concurrency != 1:
                raise ValueError('This preregistered experiment requires concurrency=1')
            super().__init__(config)
            self.pass_number = 1
            self.attempts = []
            self.items = {}
            self.retry_decisions = []

        async def _run_single(self, item):
            self.items[item['task_id']] = item
            state = dict(task_id=item['task_id'], task_type=item['task_type'],
                         pass_number=self.pass_number, requests=[])
            state['pass'] = self.pass_number
            token = ACTIVE.set(state)
            before = self.budget_tracker.spent_effective_tokens
            try:
                result = await super()._run_single(item)
            finally:
                ACTIVE.reset(token)
            self.attempts.append(dict(task_id=item['task_id'], pass_number=self.pass_number,
                result=asdict(result), effective_cost_delta=round(self.budget_tracker.spent_effective_tokens-before, 6),
                requests=state['requests']))
            return result

        async def run_all(self):
            summary = await super().run_all()
            first = list(self.attempts)
            self.pass_number = 2
            for attempt in first:
                task_id = attempt['task_id']
                item = self.items[task_id]
                status = attempt['result']['status']
                shortened = any(r['requested_cap'] > r['first_cap'] for r in attempt['requests'])
                events = [e for e in self.budget_tracker.events if e['task_id'] == task_id and e['status'] != 'NOT_SENT']
                eligible = status in ('TRUNCATED', 'FAILED') and shortened and bool(events)
                decision = dict(task_id=task_id, first_status=status, eligible=eligible, retried=False)
                if eligible:
                    requested = max(r['requested_cap'] for r in attempt['requests'])
                    minimum = min(requested, 2*caps.get(item['task_type'], requested))
                    admission = max(e['input_token_estimate'] for e in events)/10 + minimum
                    decision.update(required_reserve=admission, remaining=self.budget_tracker.remaining)
                    accounted = all(e['status']=='ACCOUNTED' for e in events)
                    allowed = (accounted and not self.budget_tracker.proxy_exhausted
                               and not self.budget_tracker.has_unaccounted_request
                               and self.budget_tracker.remaining >= admission)
                    if allowed:
                        await self._run_single(item)
                        decision['retried'] = True
                    else:
                        decision['reason'] = 'insufficient_reserve_or_accounting_stop'
                self.retry_decisions.append(decision)
            solved = [task_id for task_id,r in self.results.items() if r['status']=='SOLVED']
            summary.update(task_results=self.results, solved_count=len(solved),
                estimated_score=sum(self.items[n]['reward'] for n in solved),
                effective_tokens_spent=self.budget_tracker.spent_effective_tokens,
                budget_state=self.budget_tracker.snapshot(), workflow_runs=self.task_runner.runs,
                two_pass=dict(first_caps=caps, attempts=self.attempts, decisions=self.retry_decisions))
            return summary
    return TwoPassScheduler

def capped_completion(original, caps):
    async def complete(bridge, model, system_prompt, user_prompt, max_tokens=512, temperature=0.0):
        state = ACTIVE.get()
        cap = max_tokens
        if state and state['pass'] == 1:
            cap = min(cap, caps.get(state['task_type'], max_tokens))
        if state is not None:
            state['requests'].append(dict(requested_cap=max_tokens, first_cap=cap, model=model))
        return await original(bridge, model, system_prompt, user_prompt, max_tokens=cap, temperature=temperature)
    return complete

async def run(args):
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if plan['arm']=='baseline':
        return await bench.run(args)
    if plan['arm']!='two_pass':raise ValueError('Unknown arm')
    caps=plan['first_caps']
    if any(type(v) is not int or v<1 for v in caps.values()):raise ValueError('Invalid cap')
    with patch.object(bench, 'TaskScheduler', scheduler_type(caps)), \
         patch('harness.planner.scheduler.BudgetTracker', RetryTracker), \
         patch.object(OpenJiuwenLLMBridge, 'complete', capped_completion(OpenJiuwenLLMBridge.complete, caps)):
        return await bench.run(args)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
