"""Оценка ожидаемого расхода токенов E[tokens] и вероятности успеха P(solvable)."""
import pickle
from pathlib import Path
from typing import Tuple

from harness.config import TaskFeatures


class TokenCostEstimator:
    """
    Гибридный оценщик: использует предрасчитанные базовые профили расхода по типам задач
    или загружает обученную классическую регрессию из harness/models_weights/cost_regressor.pkl.
    """

    def __init__(self, weights_dir: Path | None = None) -> None:
        self.regressor = None
        self.clf = None
        if weights_dir:
            reg_path = weights_dir / "cost_regressor.pkl"
            clf_path = weights_dir / "solvability_clf.pkl"
            if reg_path.exists():
                try:
                    self.regressor = pickle.loads(reg_path.read_bytes())
                except Exception:
                    self.regressor = None
            if clf_path.exists():
                try:
                    self.clf = pickle.loads(clf_path.read_bytes())
                except Exception:
                    self.clf = None

    def estimate(self, features: TaskFeatures) -> Tuple[float, float]:
        """Возвращает (p_solvable, expected_effective_tokens)."""
        if features.missing_entity_or_column or features.conflicting_tests_detected:
            return 0.0, 999999.0

        # Базовые оценки (в приведённых выходных токенах: in/10 + out)
        # для оптимизированных пайплайнов (локальный расчёт + ультракороткий вызов noreason)
        if features.task_type == "search":
            base_cost = 65.0 + 0.5 * features.kb_files_count
            p_solv = 0.96
        elif features.task_type == "data_analysis":
            base_cost = 85.0
            p_solv = 0.95
        elif features.task_type == "math":
            base_cost = 95.0 + 0.05 * features.instruction_len
            p_solv = 0.93
        elif features.task_type == "coding":
            # Если тесты уже проходят или нужно поправить 1-2 функции
            fail_factor = max(1, features.initial_tests_failed)
            base_cost = 160.0 + 45.0 * fail_factor + 0.02 * features.total_bytes
            p_solv = 0.88 if fail_factor <= 3 else 0.70
        else:
            base_cost = 350.0
            p_solv = 0.65

        return p_solv, max(base_cost, 25.0)
