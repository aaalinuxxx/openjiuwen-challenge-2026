#!/usr/bin/env python3
"""Генератор синтетического тренировочного пула (100 задач, включая 20% невыполнимых)."""
import argparse
import json
import random
from pathlib import Path


def generate_pool(out_dir: Path, count: int = 20, seed: int = 42) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        ttype = rng.choice(["coding", "data_analysis", "math", "search"])
        unsolvable = (i % 5 == 0)  # 20% невыполнимых задач
        reward = rng.randint(1, 10)
        tid = f"{ttype}_{i:04d}"
        tdir = out_dir / tid
        tdir.mkdir(parents=True, exist_ok=True)

        if ttype == "math":
            start = rng.randint(500, 2000)
            div = 0 if unsolvable else rng.choice([2, 3])
            instruction = (
                f"A warehouse starts with {start} boxes. "
                f"Then the stock is split equally into {div} warehouses and it keeps one share (rounded down). "
                "How many boxes does it have at the end? Write ONLY the final answer to answer.txt."
            )
            expected = "UNSOLVABLE" if unsolvable else str(start // div)
            (tdir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": tid,
                        "task_type": "math",
                        "instruction": instruction,
                        "reward": reward,
                        "expected": expected,
                        "unsolvable": unsolvable,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            # Шаблонная заглушка для остальных типов
            (tdir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": tid,
                        "task_type": ttype,
                        "instruction": f"Synthetic {ttype} task #{i}",
                        "reward": reward,
                        "unsolvable": unsolvable,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, default=Path("./synthetic_tasks"))
    p.add_argument("--count", type=int, default=20)
    args = p.parse_args()
    generate_pool(args.out_dir, args.count)
    print(f"Сгенерировано {args.count} задач в {args.out_dir}")
