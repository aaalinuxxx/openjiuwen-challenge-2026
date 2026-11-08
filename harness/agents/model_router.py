"""Маршрутизация между 4 разрешёнными моделями Qwen."""
from harness.config import (
    MODEL_QWEN_27B_NOREASON,
    MODEL_QWEN_27B_REASON,
    MODEL_QWEN_35B_NOREASON,
    TaskContext,
)


def select_primary_model(ctx: TaskContext) -> str:
    """
    Выбирает стартовую модель без рассуждений (-noreason),
    чтобы не сжигать выходные токены на <think> блок.
    """
    if ctx.task_type in ("search", "data_analysis"):
        return MODEL_QWEN_35B_NOREASON
    return MODEL_QWEN_27B_NOREASON


def select_fallback_model(ctx: TaskContext) -> str | None:
    """Переключает на мощную модель при неудаче первой попытки."""
    if ctx.task_type in ("search", "data_analysis"):
        return MODEL_QWEN_27B_NOREASON
    if ctx.allow_reasoning_escalation:
        return MODEL_QWEN_27B_REASON
    return None
