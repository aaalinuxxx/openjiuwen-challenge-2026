"""Run the actual scheduler on tasks at zero API budget."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import HarnessConfig
from harness.planner.scheduler import TaskScheduler


async def main():
    # Проверяем доступные директории с задачами
    candidates = [
        ROOT / 'synthetic_dev_pool',
        ROOT.parent / 'task-dir' / 'task-dir',
        ROOT.parent / 'task-dir',
        ROOT / 'task-dir',
    ]
    source = None
    for cand in candidates:
        if cand.exists() and any(cand.glob('*/task.json')):
            source = cand
            break

    if not source:
        print("Ошибка: папка с задачами не найдена!")
        return

    print(f"Запуск шедулера на задачах из: {source}")
    task_dirs = [p for p in source.iterdir() if p.is_dir() and (p / 'task.json').exists()]
    print(f"Найдено папок задач: {len(task_dirs)}")

    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='oj-main-offline-') as tmp:
        directory = Path(tmp) / 'tasks'
        directory.mkdir()
        truths = {}
        for tdir in task_dirs:
            task_json = tdir / 'task.json'
            data = json.loads(task_json.read_text(encoding='utf-8'))
            truths[tdir.name] = data
            target = directory / tdir.name
            shutil.copytree(tdir, target)
            (target / 'task.json').write_text(
                json.dumps({k: v for k, v in data.items() if k not in ('expected', 'unsolvable')}),
                encoding='utf-8'
            )
            for answer in target.rglob('answer.txt'):
                answer.unlink()

        scheduler = TaskScheduler(
            HarnessConfig(
                directory,
                None,
                os.environ.get('LLM_BASE_URL', 'https://api.neuraldeep.ru/v1'),
                os.environ.get('LLM_API_KEY', 'sk-qxTfP0UOoB4TA9vtBb2QwA'),
                initial_budget_tokens=5000,
                execution_engine='direct'
            )
        )
        summary = await scheduler.run_all()
        rows = []
        for name, truth in truths.items():
            path = directory / name / 'answer.txt'
            answer = path.read_text(encoding='utf-8').strip() if path.exists() else None
            is_unsolvable = truth.get('unsolvable', False)
            expected = str(truth.get('expected', ''))

            # Для невыполнимых: правильно, если answer.txt НЕ создан
            if is_unsolvable:
                correct = (answer is None)
            else:
                correct = (answer == expected) if expected else (answer is not None)

            rows.append(
                dict(
                    task_id=name,
                    task_type=truth.get('task_type'),
                    answer=answer,
                    expected=expected,
                    unsolvable=is_unsolvable,
                    correct=correct,
                    reward=truth.get('reward', 1)
                )
            )

    assert all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in originals.items())

    correct_count = sum(1 for r in rows if r['correct'])
    score_count = sum(r['reward'] for r in rows if r['correct'] and not r['unsolvable'])

    report = dict(
        scope='actual scheduler on synthetic dev pool at zero budget',
        total_tasks=len(rows),
        correct_behaviors=correct_count,
        earned_score=score_count,
        summary=summary,
        rows=rows
    )

    out_file = ROOT / 'experiments' / 'E33_synthetic_scheduler_zero_budget.json'
    with out_file.open('w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n=== Итог прогона шедулера на 40 задачах (Zero Budget) ===")
    print(f"Всего задач в пуле: {len(rows)}")
    print(f"Корректных решений и корректных пропусков: {correct_count}/{len(rows)}")
    print(f"Набрано баллов за бесплатно решённые задачи: {score_count}")
    print(f"Потрачено токенов API: {summary.get('effective_tokens_spent', 0)}")
    print(f"Отчёт сохранён в: {out_file.name}")


if __name__ == '__main__':
    asyncio.run(main())