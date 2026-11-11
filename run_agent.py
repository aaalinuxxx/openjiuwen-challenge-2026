#!/usr/bin/env python3
"""Главная точка входа харнесса (/app/run_agent.py)."""
import os
import sys

import argparse
import asyncio
import logging
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from harness.config import HarnessConfig


def setup_logging() -> None:
    log_file = Path(tempfile.gettempdir()) / "openjiuwen_logs" / "harness.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def parse_args(argv=None) -> argparse.Namespace:
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
        default=os.environ.get("BUDGET", os.environ.get("TOKEN_BUDGET", "100000")),
        help="Опциональный известный потолок бюджета в выходных токенах",
    )
    parser.add_argument('--experimental-joins', action='store_true',
                        help='Enable experimental typed/local joins and multi-CSV fallback')
    args, _ = parser.parse_known_args(argv)
    if not math.isfinite(args.budget) or args.budget < 0:
        parser.error("budget must be finite and non-negative")
    return args


async def async_main() -> int:
    setup_logging()
    args = parse_args()
    from harness.planner.scheduler import TaskScheduler
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
        experimental_joins=args.experimental_joins,
        budget_audit_path=Path(tempfile.gettempdir()) / "openjiuwen_logs" /
            ("budget_"+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+".json"),
    )

    from harness.workflow_runner import SDKUnavailable
    try:
        scheduler = TaskScheduler(config=config)
    except SDKUnavailable as exc:
        logger.error("SDK initialization: %s", exc)
        return 2
    summary = await scheduler.run_all()
    logger.info("Budget audit: %s; unaccounted request: %s", summary["budget_audit_path"],
                summary["budget_state"]["has_unaccounted_request"])
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
