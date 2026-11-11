"""Общие структуры данных, контракты между Планировщиком и Агентами, конфигурация моделей."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


# Четыре разрешённые по регламенту модели
MODEL_QWEN_27B_NOREASON = "qwen3.8-27b-noreason"
MODEL_QWEN_27B_REASON = "qwen3.8-27b"
MODEL_QWEN_35B_NOREASON = "qwen3.6-35b-a3b-noreason"
MODEL_QWEN_35B_REASON = "qwen3.6-35b-a3b"


@dataclass
class HarnessConfig:
    tasks_dir: Path
    out_path: Optional[Path]
    llm_base_url: str
    llm_api_key: str
    max_concurrency: int = 5
    initial_budget_tokens: float = 100000.0
    tmp_root: Path = Path("/tmp/harness_work")
    reward_threshold_for_reasoning: int = 4
    reasoning_usage_mode: str = "unverified"
    budget_audit_path: Optional[Path] = None
    search_min_task_budget: float = 0.0
    data_min_task_budget: float = 0.0
    coding_min_task_budget: float = 800.0
    max_api_calls: Optional[int] = None
    execution_engine: str = "openjiuwen"


@dataclass
class TaskFeatures:
    task_id: str
    task_type: str
    reward: int
    instruction_len: int
    num_files: int
    total_bytes: int
    csv_rows: int = 0
    kb_files_count: int = 0
    initial_tests_total: int = 0
    initial_tests_failed: int = 0
    has_syntax_error: bool = False
    missing_entity_or_column: bool = False
    conflicting_tests_detected: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """Единый входной контракт для Участника 1 (solve_task)."""
    task_id: str
    task_type: str
    instruction: str
    reward: int
    task_dir: Path
    workspace_dir: Path
    max_token_budget: float
    allow_reasoning_escalation: bool
    features: Optional[TaskFeatures] = None


@dataclass
class SolveResult:
    """Единый выходной контракт от Участника 1 для Планировщика (Участника 2)."""
    task_id: str
    status: str  # "SOLVED", "UNSOLVABLE", "BUDGET_EXCEEDED", "FAILED"
    answer: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    wall_time_sec: float = 0.0
    model_used: str = MODEL_QWEN_27B_NOREASON
    notes: str = ""

    @property
    def effective_cost(self) -> float:
        """По регламенту: 10 входных = 1 выходной, токены рассуждений считаются как выходные."""
        return (self.input_tokens / 10.0) + float(self.output_tokens) + float(self.reasoning_tokens)
