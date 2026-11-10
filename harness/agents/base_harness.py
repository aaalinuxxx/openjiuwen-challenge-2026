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

import json
import random

class ProxyBudgetExhausted(BudgetDenied):
    """Вызывается, когда прокси вернул 401/402/403 (лимит токенов хакатона исчерпан)."""
    pass

class TransientNetworkError(Exception):
    """Временный сетевой сбой (таймаут, 502, 503)."""
    pass


class RobustHTTPTransport:
    """Отказоустойчивый транспорт с гранулярными политиками под каждый тип сбоя."""

    def __init__(self, base_url: str, api_key: str, max_retries: int = 3):
        self.base_url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.max_retries = max_retries
        self._proxy_exhausted = False

    async def send(self, payload: dict) -> dict:
        import httpx

        if self._proxy_exhausted:
            raise ProxyBudgetExhausted("Прокси организаторов отключил доступ (лимит токенов выбран)")

        last_error = None

        for attempt in range(self.max_retries):
            # Экспоненциальный джиттер для предотвращения резонанса запросов
            jitter = random.uniform(0.1, 0.8)

            try:
                # На каждую попытку настраиваем чёткие тайм-ауты (10с на коннект, 60с на генерацию)
                limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
                timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

                async with httpx.AsyncClient(limits=limits, timeout=timeout, verify=True) as client:
                    response = await client.post(self.base_url, headers=self.headers, json=payload)

                    # 1. СТРАТЕГИЯ: Жесткий стоп по бюджету (401, 402, 403)
                    if response.status_code in (401, 402, 403):
                        self._proxy_exhausted = True
                        logger.error(
                            "Стена бюджета! Прокси вернул HTTP %d: %s",
                            response.status_code, response.text[:200]
                        )
                        raise ProxyBudgetExhausted(f"HTTP {response.status_code}: Token limit reached")

                    # 2. СТРАТЕГИЯ: Превышение частоты запросов (429 Too Many Requests)
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            wait_time = float(retry_after) + jitter
                        else:
                            wait_time = (2.0 ** (attempt + 1)) + jitter
                        logger.warning(
                            "[429 RateLimit] Попытка %d/%d. Пауза %.2f с перед повтором...",
                            attempt + 1, self.max_retries, wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    # 3. СТРАТЕГИЯ: Временные сбои GPU-серверов или шлюза (500, 502, 503, 504)
                    if response.status_code in (500, 502, 503, 504):
                        wait_time = 1.5 * (attempt + 1) + jitter
                        logger.warning(
                            "[HTTP %d ServerError] Попытка %d/%d. Перезапрос через %.2f с...",
                            response.status_code, attempt + 1, self.max_retries, wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    # 4. Проверка остальных клиентских ошибок (400 Bad Request, 404 Not Found)
                    if response.status_code >= 400:
                        logger.error("Неисправимая ошибка запроса HTTP %d: %s", response.status_code, response.text[:300])
                        response.raise_for_status()

                    # 5. СТРАТЕГИЯ: Защита от поврежденного JSON (HTML от Nginx или обрыв)
                    try:
                        data = response.json()
                    except json.JSONDecodeError as json_err:
                        logger.warning("Ответ сервера не является валидным JSON: %s", response.text[:200])
                        await asyncio.sleep(1.0 + jitter)
                        continue

                    # Валидация структуры ответа
                    if not isinstance(data, dict) or "choices" not in data:
                        logger.warning("Некорректная структура payload: отсутствует 'choices'")
                        await asyncio.sleep(1.0 + jitter)
                        continue

                    # 6. СТРАТЕГИЯ: Детекция обрезки по длине finish_reason == 'length'
                    finish_reason = data["choices"][0].get("finish_reason")
                    if finish_reason == "length":
                        logger.warning("Ответ модели был обрезан по лимиту max_tokens!")

                    # Успех: возвращаем проверенный JSON
                    return data

            except httpx.ConnectTimeout:
                last_error = TransientNetworkError("Таймаут подключения к серверу API")
                wait_time = 2.0 + jitter
                logger.warning("[ConnectTimeout] Сервер не ответил за 10с. Повтор через %.2f с...", wait_time)
                await asyncio.sleep(wait_time)

            except httpx.ReadTimeout:
                last_error = TransientNetworkError("Таймаут чтения генерации (сервер думал > 60с)")
                wait_time = 1.0 + jitter
                logger.warning("[ReadTimeout] Генерация превысила 60с. Повтор через %.2f с...", wait_time)
                await asyncio.sleep(wait_time)

            except (httpx.ConnectError, httpx.NetworkError) as net_err:
                last_error = TransientNetworkError(f"Сетевой разрыв: {type(net_err).__name__}")
                wait_time = 2.0 * (attempt + 1) + jitter
                logger.warning("[NetworkError] %s. Повтор через %.2f с...", type(net_err).__name__, wait_time)
                await asyncio.sleep(wait_time)

            except ProxyBudgetExhausted:
                raise

            except Exception as exc:
                logger.error("Критическое исключение в транспорте: %s", exc)
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Не удалось получить ответ от LLM API после всех попыток")

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
        robust_transport = RobustHTTPTransport(
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            max_retries=3
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
            data=await transport(payload)
            counts=parse_usage(data,mode)
            await self.tracker.settle(ticket,*counts)
            content=data['choices'][0]['message']['content']
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
