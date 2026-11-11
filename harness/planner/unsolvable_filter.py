"""Фильтрация невыполнимых задач (Zero-Token + проверка аномалий)."""
from harness.agents.calculation_plans import parse_warehouse_plan, execute_warehouse_plan
from typing import Tuple

from harness.config import TaskFeatures


def check_unsolvable_zero_token(instruction: str, features: TaskFeatures) -> Tuple[bool, str]:
    """
    Возвращает (is_unsolvable, reason).
    Работает за 0 токенов до обращения к прокси.
    """
    if not instruction.strip():
        return True, "Пустая инструкция задачи"

    if features.missing_entity_or_column:
        return True, f"Отсутствуют необходимые данные/сущности в {features.task_type}"

    if features.conflicting_tests_detected:
        # Textually identical expressions can observe different state/fixtures.
        # Preserve this feature as a warning, not proof of impossibility.
        return False, "UNKNOWN: возможный конфликт тестов требует проверки состояния"

    if features.task_type == "math":
        # A keyword in a warning, quote or conditional is not an operation.
        # Only a complete recognized plan supplies a local impossibility proof.
        plan = parse_warehouse_plan(instruction)
        if plan is not None and execute_warehouse_plan(plan) == "UNSOLVABLE":
            return True, "Division by zero in a fully parsed arithmetic plan"

    return False, "OK"
