#!/usr/bin/env python3
"""Скрипт обучения классических моделей оценки расхода токенов (Ridge / GBDT) по логам траекторий."""
import json
import pickle
from pathlib import Path
import numpy as np
from sklearn.linear_model import Ridge

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "harness" / "models_weights"


def train_dummy_baseline() -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    X = np.array([[100, 1, 500], [300, 2, 1200], [500, 36, 2500], [250, 0, 0]], dtype=float)
    y = np.array([85.0, 180.0, 70.0, 95.0], dtype=float)
    model = Ridge(alpha=1.0)
    model.fit(X, y)
    (WEIGHTS_DIR / "cost_regressor.pkl").write_bytes(pickle.dumps(model))
    print("Сохранены базовые веса оценщика в", WEIGHTS_DIR / "cost_regressor.pkl")


if __name__ == "__main__":
    train_dummy_baseline()
