"""Solver dispatch and budgeted HTTP bridge, invoked by workflow_runner."""
import asyncio
import logging
import time

from harness.config import HarnessConfig, TaskContext, SolveResult
from harness.planner.budget_tracker import BudgetDenied, BudgetTracker
from harness.agents.coding_solver import solve_coding_task
from harness.agents.data_solver import solve_data_task
from harness.agents.math_solver import solve_math_task
from harness.agents.search_solver import solve_search_task
from harness.agents.fallback_react import solve_fallback_task

logger = logging.getLogger('base_harness')

"""One HTTP attempt per ledger reservation; response interpretation is upstream."""
class APIHTTPError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        self.category = {401: 'AUTHENTICATION', 402: 'PAYMENT_REQUIRED',
                         403: 'ACCESS_DENIED', 429: 'RATE_LIMIT'}.get(status_code, 'HTTP_ERROR')
        super().__init__(f'{self.category}: HTTP {status_code}')


class TruncatedGeneration(RuntimeError):
    pass


class RobustHTTPTransport:
    """No automatic retries: a failed response can still have incurred cost."""
    def __init__(self, base_url, api_key):
        self.url = base_url.rstrip('/') + '/chat/completions'
        self.api_key = api_key

    async def send(self, payload):
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0),
                                     verify=True, follow_redirects=False) as client:
            response = await client.post(self.url,
                headers={'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json'},
                json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise APIHTTPError(exc.response.status_code) from None
            # Do not examine choices here: known usage must be recorded first.
            return response.json()

class UnverifiedAccounting(BudgetDenied):
    pass


def parse_usage(data, mode='unverified'):
    """Explicit reasoning contract; never infer inclusion by comparing sizes."""
    usage=data.get('usage')
    if not isinstance(usage,dict): raise ValueError('Missing usage')
    inp,out=usage['prompt_tokens'],usage['completion_tokens']
    details=usage.get('completion_tokens_details') or {}
    if not isinstance(details,dict): raise ValueError('Invalid details')
    nested,root=details.get('reasoning_tokens'),usage.get('reasoning_tokens')
    if nested is not None and root is not None and nested!=root:
        raise ValueError('Conflicting reasoning counts')
    reasoning=nested if nested is not None else (root if root is not None else 0)
    if any(type(v) is not int or v<0 for v in (inp,out,reasoning)):
        raise ValueError('Invalid token counts')
    if mode not in ('unverified','included','separate'): raise ValueError('Invalid accounting mode')
    if reasoning:
        if mode=='unverified': raise ValueError('Reasoning billing contract unverified')
        if mode=='included':
            if reasoning>out: raise ValueError('Inconsistent included reasoning')
            out-=reasoning
    return inp,out,reasoning


class OpenJiuwenLLMBridge:
    """Budgeted HTTP transport; openJiuwen orchestration lives in workflow_runner."""
    def __init__(self, config, tracker=None, ctx=None, transport=None):
        self.config=config
        self.tracker=tracker if tracker is not None else BudgetTracker(config.initial_budget_tokens)
        self.task_id=ctx.task_id if ctx else 'standalone'
        self.task_budget=ctx.max_token_budget if ctx else config.initial_budget_tokens
        self.transport=transport

    def _get_transport(self):
        if self.transport is not None:
            return self.transport
        import httpx  # Resolve local dependency before attempting transport.
        robust_transport = RobustHTTPTransport(
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key
        )
        return robust_transport.send

    async def complete(self, model, system_prompt, user_prompt, max_tokens=512, temperature=0.0):
        mode=self.config.reasoning_usage_mode
        if not model.endswith('-noreason') and mode=='unverified':
            raise UnverifiedAccounting('Reasoning billing contract not verified')
        estimate=len((system_prompt+user_prompt).encode('utf-8'))+1024
        ticket,cap=await self.tracker.reserve(self.task_id,self.task_budget,estimate,max_tokens)
        payload=dict(model=model,messages=[dict(role='system',content=system_prompt),
                     dict(role='user',content=user_prompt)],max_tokens=cap,temperature=temperature)
        try:
            transport=self._get_transport()
        except Exception as exc:
            await self.tracker.not_sent(ticket,type(exc).__name__)
            raise
        try:
            data=await asyncio.wait_for(transport(payload), timeout=self.config.request_timeout_sec)
            counts=parse_usage(data,mode)
            await self.tracker.settle(ticket,*counts)
            choice=data['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise TruncatedGeneration('Output limit reached; usage accounted')
            content=choice['message']['content']
            if not isinstance(content,str): raise ValueError('Invalid content')
            return content.strip(),*counts
        except asyncio.CancelledError:
            await asyncio.shield(self.tracker.unknown(ticket,'CancelledError'))
            raise
        except Exception as exc:
            await self.tracker.unknown(ticket,type(exc).__name__)
            raise


async def solve_task(ctx: TaskContext, config: HarnessConfig, budget_tracker=None, transport=None) -> SolveResult:
    started=time.monotonic()
    bridge=OpenJiuwenLLMBridge(config,budget_tracker,ctx,transport)
    try:
        solver={'search':solve_search_task,'data_analysis':solve_data_task,'math':solve_math_task,
                'coding':solve_coding_task}.get(ctx.task_type,solve_fallback_task)
        result=await solver(ctx,bridge)
    except APIHTTPError as exc:
        result=SolveResult(task_id=ctx.task_id,status='API_'+exc.category,notes=str(exc))
    except TruncatedGeneration as exc:
        result=SolveResult(task_id=ctx.task_id,status='TRUNCATED',notes=str(exc))
    except UnverifiedAccounting as exc:
        result=SolveResult(task_id=ctx.task_id,status='ACCOUNTING_UNVERIFIED',notes=str(exc))
    except BudgetDenied as exc:
        attempted=any(e['task_id']==ctx.task_id and e['status']!='NOT_SENT' for e in bridge.tracker.events)
        # Re-running a partially paid solver would duplicate earlier calls.
        can_defer=exc.retryable and not attempted
        result=SolveResult(task_id=ctx.task_id,status='DEFERRED_BUDGET' if can_defer else 'BUDGET_EXCEEDED',notes=str(exc))
    except Exception as exc:
        logger.warning('Task %s failed: %s',ctx.task_id,type(exc).__name__)
        uncertain=any(e['task_id']==ctx.task_id and e['status']=='COST_UNKNOWN_STOPPED' for e in bridge.tracker.events)
        result=SolveResult(task_id=ctx.task_id,status='ACCOUNTING_UNKNOWN' if uncertain else 'FAILED',
                           notes=type(exc).__name__)
    result.input_tokens,result.output_tokens,result.reasoning_tokens=bridge.tracker.usage_for_task(ctx.task_id)
    result.wall_time_sec=time.monotonic()-started
    return result
