"""Отслеживание глобального бюджета токенов и политики Early Stopping (BAGEN)."""
import asyncio
from dataclasses import dataclass


@dataclass
class BudgetTracker:
    max_budget: float
    spent_effective_tokens: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    proxy_exhausted: bool = False

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    async def record_usage(self, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> float:
        async with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_reasoning_tokens += reasoning_tokens
            delta = (input_tokens / 10.0) + float(output_tokens) + float(reasoning_tokens)
            self.spent_effective_tokens += delta
            return self.spent_effective_tokens

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_budget - self.spent_effective_tokens)

    def allocate_task_budget(self, expected_cost: float, reward: int) -> float:
        """Выделяет потолок токенов на конкретную задачу с запасом под размер награды."""
        multiplier = 1.8 if reward <= 2 else 2.5
        return min(self.remaining, expected_cost * multiplier)
