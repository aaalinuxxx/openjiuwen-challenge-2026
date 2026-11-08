#!/usr/bin/env python3
"""Главная точка входа харнесса (/app/run_agent.py)."""
import os
import sys

# Важно: перенаправляем HOME и рабочие логи в /tmp ДО импорта openJiuwen,
# так как контейнер запускается с флагом --read-only.
os.environ.setdefault("HOME", "/tmp")
os.makedirs("/tmp/openjiuwen_logs", exist_ok=True)

import argparse
import asyncio
import logging
from pathlib import Path

from harness.config import HarnessConfig
from harness.planner.scheduler import TaskScheduler


def setup_logging() -> None:
    log_file = Path("/tmp/openjiuwen_logs/harness.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="openJiuwen Budget-Aware Agent Harness")
    parser.add_argument(
        "--tasks-dir",
        type=str,
        default=os.environ.get("TASKS", "/data/tasks"),
        help="Каталог с задачами (100 подкаталогов с task.json)",
    )
    parser.add_argument(
        "--out-file",
        type=str,
        default=os.environ.get("OUT", ""),
        help="Опциональный путь к сводному выходному файлу решений",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=5,
        help="Максимальное число параллельных сессий агента (по регламенту до 5)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=float(os.environ.get("TOKEN_BUDGET", "1e9")),
        help="Опциональный известный потолок бюджета в выходных токенах",
    )
    args, _ = parser.parse_known_args()
    return args


async def async_main() -> int:
    setup_logging()
    args = parse_args()
    logger = logging.getLogger("run_agent")

    tasks_dir = Path(args.tasks_dir).resolve()
    if not tasks_dir.exists():
        logger.error("Каталог задач не найден: %s", tasks_dir)
        return 1

    config = HarnessConfig(
        tasks_dir=tasks_dir,
        out_path=Path(args.out_file) if args.out_file else None,
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY", "dummy-key"),
        max_concurrency=min(max(args.max_concurrency, 1), 5),
        initial_budget_tokens=args.budget,
    )

    scheduler = TaskScheduler(config=config)
    summary = await scheduler.run_all()
    logger.info(
        "Завершено. Решено задач: %d/%d | Набрано баллов (оценка): %d | Потрачено приведённых токенов: %.1f",
        summary["solved_count"],
        summary["total_tasks"],
        summary["estimated_score"],
        summary["effective_tokens_spent"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
