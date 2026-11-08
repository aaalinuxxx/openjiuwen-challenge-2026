"""Фильтрация невыполнимых задач (Zero-Token + проверка аномалий)."""
import re
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
        return True, "Обнаружены взаимоисключающие assertEqual в тестах"

    if features.task_type == "math":
        if re.search(r"split equally into 0\b|divide by 0\b", instruction, re.IGNORECASE):
            return True, "Деление на ноль в условии math задачи"

    return False, "OK"
