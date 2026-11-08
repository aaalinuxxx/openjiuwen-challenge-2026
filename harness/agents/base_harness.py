"""Базовый коннектор к openJiuwen и диспетчеризация задач по доменным солверам."""
import logging
import time
from typing import Dict, Any, Tuple

import httpx

from harness.config import HarnessConfig, TaskContext, SolveResult
from harness.agents.coding_solver import solve_coding_task
from harness.agents.data_solver import solve_data_task
from harness.agents.math_solver import solve_math_task
from harness.agents.search_solver import solve_search_task
from harness.agents.fallback_react import solve_fallback_task

logger = logging.getLogger("base_harness")


class OpenJiuwenLLMBridge:
    """
    Унифицированный мост для вызова LLM через openJiuwen SDK (если инициализирован)
    или напрямую через OpenAI-совместимый прокси организаторов с точным подсчётом
    input_tokens, output_tokens и reasoning_tokens.
    """

    def __init__(self, config: HarnessConfig) -> None:
        self.config = config
        self.base_url = config.llm_base_url.rstrip("/")
        self.api_key = config.llm_api_key

    async def complete(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Tuple[str, int, int, int]:
        """
        Возвращает (text, input_tokens, output_tokens, reasoning_tokens).
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        content = (choice.get("content") or "").strip()

        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))

        # Извлекаем токены рассуждений из всех возможных полей API
        details = usage.get("completion_tokens_details") or {}
        reasoning_tok = int(
            details.get("reasoning_tokens", 0)
            or usage.get("reasoning_tokens", 0)
        )
        # Если провайдер уже включил reasoning_tokens в completion_tokens, не дублируем
        if reasoning_tok > 0 and out_tok >= reasoning_tok:
            out_tok = out_tok - reasoning_tok

        return content, in_tok, out_tok, reasoning_tok


async def solve_task(ctx: TaskContext, config: HarnessConfig) -> SolveResult:
    """Главный диспетчер задачи (Точка входа Участника 1)."""
    t0 = time.monotonic()
    bridge = OpenJiuwenLLMBridge(config)

    try:
        if ctx.task_type == "search":
            res = await solve_search_task(ctx, bridge)
        elif ctx.task_type == "data_analysis":
            res = await solve_data_task(ctx, bridge)
        elif ctx.task_type == "math":
            res = await solve_math_task(ctx, bridge)
        elif ctx.task_type == "coding":
            res = await solve_coding_task(ctx, bridge)
        else:
            res = await solve_fallback_task(ctx, bridge)
    except Exception as exc:
        logger.warning("Ошибка при решении %s: %s", ctx.task_id, exc)
        res = SolveResult(task_id=ctx.task_id, status="FAILED", notes=str(exc))

    res.wall_time_sec = time.monotonic() - t0
    return res
