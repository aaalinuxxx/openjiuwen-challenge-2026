"""Планировщик очереди задач по ROI = (reward * P_solvable) / E[tokens]."""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

from harness.config import HarnessConfig, TaskContext, SolveResult
from harness.planner.budget_tracker import BudgetTracker
from harness.planner.feature_extractor import extract_task_features
from harness.planner.token_estimator import TokenCostEstimator
from harness.planner.unsolvable_filter import check_unsolvable_zero_token
from harness.agents.base_harness import solve_task
from harness.sandbox.file_guard import save_task_answer

logger = logging.getLogger("scheduler")


class TaskScheduler:
    def __init__(self, config: HarnessConfig) -> None:
        self.config = config
        self.estimator = TokenCostEstimator(
            weights_dir=Path(__file__).resolve().parent.parent / "models_weights"
        )
        self.budget_tracker = BudgetTracker(max_budget=config.initial_budget_tokens)
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
            if self.budget_tracker.proxy_exhausted or self.budget_tracker.remaining <= 5.0:
                return SolveResult(task_id=item["task_id"], status="BUDGET_EXCEEDED")

            task_budget = self.budget_tracker.allocate_task_budget(
                expected_cost=item["expected_cost"], reward=item["reward"]
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

            res = await solve_task(ctx, self.config)
            await self.budget_tracker.record_usage(
                res.input_tokens, res.output_tokens, res.reasoning_tokens
            )

            if res.status == "SOLVED" and res.answer is not None:
                save_task_answer(
                    task_dir=ctx.task_dir,
                    workspace_dir=ctx.workspace_dir,
                    task_id=ctx.task_id,
                    answer=res.answer,
                    global_out_path=self.config.out_path,
                )
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
        for i in range(0, len(ranked), batch_size):
            if self.budget_tracker.proxy_exhausted:
                break
            batch = ranked[i : i + batch_size]
            results = await asyncio.gather(*(self._run_single(item) for item in batch))
            for item, res in zip(batch, results):
                if res.status == "SOLVED":
                    solved_count += 1
                    estimated_score += int(item["reward"])

        return {
            "total_tasks": len(ranked),
            "solved_count": solved_count,
            "estimated_score": estimated_score,
            "effective_tokens_spent": self.budget_tracker.spent_effective_tokens,
        }
