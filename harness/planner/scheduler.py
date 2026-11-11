"""Планировщик очереди задач по ROI = (reward * P_solvable) / E[tokens]."""
from dataclasses import asdict
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

from harness.config import HarnessConfig, TaskContext, SolveResult
from harness.planner.budget_tracker import BudgetTracker
from harness.planner.feature_extractor import extract_task_features
from harness.planner.token_estimator import TokenCostEstimator
from harness.planner.unsolvable_filter import check_unsolvable_zero_token
from harness.workflow_runner import task_runner

logger = logging.getLogger("scheduler")


class TaskScheduler:
    def __init__(self, config: HarnessConfig) -> None:
        if type(config.max_concurrency) is not int or not 1 <= config.max_concurrency <= 5:
            raise ValueError('max_concurrency must be an integer from 1 to 5')
        self.config = config
        self.results = {}
        self.skipped_tasks = {}
        self.estimator = TokenCostEstimator(
            weights_dir=Path(__file__).resolve().parent.parent / "models_weights"
        )
        self.budget_tracker = BudgetTracker(max_budget=config.initial_budget_tokens, audit_path=config.budget_audit_path, max_requests=config.max_api_calls)
        self.task_runner = task_runner(config,self.budget_tracker)
        self.semaphore = asyncio.Semaphore(config.max_concurrency)

    def discover_and_rank_tasks(self) -> List[Dict[str, Any]]:
        task_dirs = sorted(
            [p for p in self.config.tasks_dir.iterdir() if p.is_dir() and (p / "task.json").exists()]
        )
        candidates: List[Dict[str, Any]] = []

        for tdir in task_dirs:
            try:
                meta, features = extract_task_features(tdir)
                instruction = str(meta.get("instruction", ""))
                is_unsolvable, reason = check_unsolvable_zero_token(instruction, features)
                if is_unsolvable:
                    self.skipped_tasks[features.task_id] = reason
                    logger.info(
                        "[SKIP Zero-Token] %s (reward=%d): %s",
                        features.task_id,
                        features.reward,
                        reason,
                    )
                    continue

                p_solv, expected_cost = self.estimator.estimate(features)
                roi = (features.reward * p_solv) / max(expected_cost, 1.0)
                workspace_dir = tdir / "workspace" if (tdir / "workspace").exists() else tdir

                candidates.append(
                    {
                        "task_id": features.task_id,
                        "task_type": features.task_type,
                        "instruction": instruction,
                        "reward": features.reward,
                        "task_dir": tdir,
                        "workspace_dir": workspace_dir,
                        "features": features,
                        "p_solv": p_solv,
                        "expected_cost": expected_cost,
                        "roi": roi,
                    }
                )
            except Exception as exc:
                logger.warning("Ошибка чтения задачи %s: %s", tdir, exc)

        # Сортируем по убыванию ROI (при равенстве — сначала более высокая награда и меньшая цена)
        candidates.sort(key=lambda x: (x["roi"], x["reward"], -x["expected_cost"]), reverse=True)
        return candidates

    async def _run_single(self, item: Dict[str, Any]) -> SolveResult:
        async with self.semaphore:
            task_budget = self.budget_tracker.allocate_task_budget(
                expected_cost=item["expected_cost"], reward=item["reward"],
                minimum=self.config.coding_min_task_budget if item["task_type"] == "coding" else 0
            )
            ctx = TaskContext(
                task_id=item["task_id"],
                task_type=item["task_type"],
                instruction=item["instruction"],
                reward=item["reward"],
                task_dir=item["task_dir"],
                workspace_dir=item["workspace_dir"],
                max_token_budget=task_budget,
                allow_reasoning_escalation=(item["reward"] >= self.config.reward_threshold_for_reasoning),
                features=item["features"],
            )

            res = await self.task_runner.run(ctx)
            self.results[ctx.task_id] = asdict(res)

            if res.status == "SOLVED" and res.answer is not None:
                logger.info(
                    "[SOLVED] %s | type=%s | reward=%d | answer=%r | cost=%.1f",
                    ctx.task_id,
                    ctx.task_type,
                    ctx.reward,
                    res.answer,
                    res.effective_cost,
                )
            else:
                logger.info(
                    "[%s] %s | type=%s | reward=%d | cost=%.1f | notes=%s",
                    res.status,
                    ctx.task_id,
                    ctx.task_type,
                    ctx.reward,
                    res.effective_cost,
                    res.notes,
                )
            return res

    async def run_all(self) -> Dict[str, Any]:
        ranked = self.discover_and_rank_tasks()
        logger.info("Отобрано выполнимых кандидатов в очередь: %d", len(ranked))

        solved_count = 0
        estimated_score = 0

        # Запускаем батчами по max_concurrency, чтобы строго соблюдать приоритет ROI
        batch_size = self.config.max_concurrency
        pending = list(ranked)
        while pending:
            batch, pending = pending[:batch_size], pending[batch_size:]
            results = await asyncio.gather(*(self._run_single(item) for item in batch))
            deferred = []
            for item, res in zip(batch, results):
                if res.status == "DEFERRED_BUDGET":
                    deferred.append(item)
                if res.status == "SOLVED":
                    solved_count += 1
                    estimated_score += int(item["reward"])
            # In-flight reservations are now settled; retry only admission
            # deferrals. Failed/paid requests are never automatically retried.
            pending = deferred + pending

        return {
            "total_tasks": len(ranked),
            "task_results": self.results,
            "skipped_tasks": self.skipped_tasks,
            "solved_count": solved_count,
            "estimated_score": estimated_score,
            "effective_tokens_spent": self.budget_tracker.spent_effective_tokens,
            "budget_state": self.budget_tracker.snapshot(),
            "budget_audit_path": str(self.config.budget_audit_path) if self.config.budget_audit_path else None,
            "execution_engine": self.config.execution_engine,
            "workflow_runs": self.task_runner.runs,
        }
