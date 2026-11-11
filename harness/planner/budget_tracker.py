"""Shared per-request ledger. Reservations are heuristic; billing is actual.

Unknown costs retain their reservation and stop new remote work. Already
admitted requests can settle. One unit = one tenth of an effective token.
"""
import asyncio
from decimal import Decimal
import json
import math
from pathlib import Path


class BudgetDenied(RuntimeError):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable=retryable


class BudgetTracker:
    def __init__(self, max_budget, audit_path=None, max_requests=None):
        if max_requests is not None and (type(max_requests) is not int or max_requests < 0):
            raise ValueError("Invalid request cap")
        self.max_requests = max_requests
        if not math.isfinite(max_budget) or max_budget < 0:
            raise ValueError('Budget must be finite and nonnegative')
        self.max_budget = max_budget
        self._limit = int(Decimal(str(max_budget))*10)
        self._spent = 0
        self._lock = asyncio.Lock()
        self.events = []
        self._task_totals = {}
        self._task_spent = {}
        self.proxy_exhausted = False
        self.has_unaccounted_request = False
        self.audit_path = Path(audit_path) if audit_path else None
        self._persist()

    @property
    def spent_effective_tokens(self): return self._spent/10

    @property
    def reserved_effective_tokens(self):
        return sum(e['reserved_units'] for e in self.events if e['status'] in ('RESERVED','COST_UNKNOWN_STOPPED'))/10

    @property
    def remaining(self):
        return max(0.0, self.max_budget-self.spent_effective_tokens-self.reserved_effective_tokens)

    def allocate_task_budget(self, expected_cost, reward, minimum=0):
        if not math.isfinite(minimum) or minimum < 0:
            raise ValueError("Invalid minimum task budget")
        return min(self.remaining, max(minimum, expected_cost*(1.8 if reward <= 2 else 2.5)))

    def usage_for_task(self, task_id):
        return tuple(self._task_totals.get(task_id, (0,0,0)))

    def snapshot(self):
        return dict(budget=self.max_budget, known_effective_tokens=self.spent_effective_tokens,
                    reserved_effective_tokens=self.reserved_effective_tokens,
                    has_unaccounted_request=self.has_unaccounted_request,
                    remote_stopped=self.proxy_exhausted, events=[dict(e) for e in self.events])

    def _persist(self):
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.audit_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.snapshot(), indent=2), encoding='utf-8')
            temporary.replace(self.audit_path)

    async def reserve(self, task_id, task_budget, input_estimate, max_output):
        if not math.isfinite(task_budget) or task_budget < 0:
            raise ValueError('Invalid task budget')
        if type(input_estimate) is not int or input_estimate < 0 or type(max_output) is not int or max_output < 1:
            raise ValueError('Invalid reservation')
        async with self._lock:
            if self.proxy_exhausted: raise BudgetDenied('Remote work stopped')
            if self.max_requests is not None and sum(e['status'] != 'NOT_SENT' for e in self.events) >= self.max_requests:
                raise BudgetDenied('Request count limit reached')
            held = sum(e['reserved_units'] for e in self.events if e['status']=='RESERVED')
            task_held = sum(e['reserved_units'] for e in self.events if e['status']=='RESERVED' and e['task_id']==task_id)
            task_limit = int(Decimal(str(task_budget))*10)
            available = min(self._limit-self._spent-held,
                            task_limit-self._task_spent.get(task_id,0)-task_held)
            cap = min(max_output, (available-input_estimate)//10)
            if cap < 1: raise BudgetDenied('Insufficient global or task reservation', retryable=held>0)
            ticket = len(self.events)
            self.events.append(dict(ticket=ticket, task_id=task_id, status='RESERVED',
                                    reserved_units=input_estimate+cap*10, task_limit_units=task_limit,
                                    input_token_estimate=input_estimate, output_cap=cap))
            try:
                self._persist()
            except Exception:
                self.events[-1]['status']='NOT_SENT'
                raise
            return ticket, cap

    async def settle(self, ticket, input_tokens, output_tokens, reasoning_tokens=0):
        counts=(input_tokens,output_tokens,reasoning_tokens)
        if any(type(v) is not int or v < 0 for v in counts): raise ValueError('Invalid usage')
        async with self._lock:
            event=self.events[ticket]
            if event['status']!='RESERVED': raise ValueError('Request already finalized')
            task_id=event['task_id']
            delta=input_tokens+10*(output_tokens+reasoning_tokens)
            self._spent+=delta
            self._task_spent[task_id]=self._task_spent.get(task_id,0)+delta
            totals=self._task_totals.setdefault(task_id,[0,0,0])
            for i,value in enumerate(counts): totals[i]+=value
            event.update(status='ACCOUNTED',input_tokens=input_tokens,output_tokens=output_tokens,
                         reasoning_tokens=reasoning_tokens,effective_cost=delta/10)
            if delta>event['reserved_units']:
                self.proxy_exhausted=True
                event['reserve_exceeded']=True
            self._persist()

    async def unknown(self, ticket, error_type):
        async with self._lock:
            event=self.events[ticket]
            if event['status']=='RESERVED':
                event.update(status='COST_UNKNOWN_STOPPED',error_type=error_type)
                self.proxy_exhausted=True
                self.has_unaccounted_request=True
                self._persist()

    async def not_sent(self, ticket, error_type):
        async with self._lock:
            event=self.events[ticket]
            if event['status']!='RESERVED': raise ValueError('Request already finalized')
            event.update(status='NOT_SENT',error_type=error_type)
            self._persist()
