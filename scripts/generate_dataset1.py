#!/usr/bin/env python3
"""
Генератор синтетического тренировочного пула для H00.
Генерирует полноценные задачи 4 типов: coding, search, data_analysis, math.
Включает контролируемую долю невыполнимых задач (unsolvable, 15-25%).
"""
import argparse
import csv
import json
import random
from pathlib import Path


CITIES = ["Tokyo", "Berlin", "Paris", "Osaka", "Lisbon", "Tallinn", "Seoul", "Warsaw", "Prague"]
COMPANIES = ["Arktika Labs", "Bluefin Systems", "Cobalt Works", "Dune Robotics", "Ember Bio", "Fjord Data", "Granite AI"]
FIRST_NAMES = ["Alice", "Bob", "Chen", "Dmitri", "Elena", "Farid", "Grace", "Hiro", "Irina", "Jonas", "Kira", "Maya", "Nikolai", "Olga", "Pavel", "Rosa", "Sergei", "Tanya"]
LAST_NAMES = ["Smith", "Novak", "Petrov", "Sato", "Ivanov", "Garcia", "Wang", "Muller", "Haddad", "Kowalski"]
PRODUCTS = ["widget", "gadget", "sprocket", "gizmo"]
REGIONS = ["north", "south", "east", "west"]


def generate_search_task(task_id: str, task_dir: Path, unsolvable: bool, rng: random.Random) -> dict:
    workspace = task_dir / "workspace"
    kb_dir = workspace / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)

    people = []
    for _ in range(12):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        name = f"{fn} {ln}"
        if name not in people:
            people.append(name)

    companies = random.sample(COMPANIES, k=min(len(COMPANIES), 5))
    company_cities = {comp: rng.choice(CITIES) for comp in companies}

    # Создаем карточки компаний
    for comp in companies:
        slug = comp.lower().replace(" ", "_")
        c_file = kb_dir / f"company_{slug}.md"
        c_file.write_text(f"# {comp}\n\nHeadquarters: {company_cities[comp]}\nFounded: {rng.randint(1950, 2015)}\n", encoding="utf-8")

    # Создаем карточки людей
    for p in people:
        slug = p.lower().replace(" ", "_")
        p_file = kb_dir / f"person_{slug}.md"
        employer = rng.choice(companies)
        mentor = rng.choice([m for m in people if m != p] or [p])
        born = rng.randint(1960, 2002)
        p_file.write_text(f"# {p}\n\nBorn: {born}\nEmployer: {employer}\nMentor: {mentor}\n", encoding="utf-8")

    target_person = rng.choice(people)
    q_type = rng.choice(["born", "headquarters"])

    if q_type == "born":
        if unsolvable:
            instruction = f"The directory kb/ contains a small knowledge base of markdown files. In which year was Phantom Ghost born? Use the file tools or bash (ls, grep, cat) to find it. Work only inside the current directory. When you are done, write ONLY the final answer to the file answer.txt in the current directory."
            expected = "UNSOLVABLE"
        else:
            instruction = f"The directory kb/ contains a small knowledge base of markdown files. In which year was {target_person} born? Use the file tools or bash (ls, grep, cat) to find it. Work only inside the current directory. When you are done, write ONLY the final answer to the file answer.txt in the current directory."
            # Считываем правильный год
            slug = target_person.lower().replace(" ", "_")
            lines = (kb_dir / f"person_{slug}.md").read_text(encoding="utf-8").splitlines()
            born_val = [ln.split(":")[1].strip() for ln in lines if "Born:" in ln][0]
            expected = born_val
    else:
        if unsolvable:
            instruction = f"The directory kb/ contains a small knowledge base of markdown files. In which city is the headquarters of Ghost Person's employer? Use the file tools or bash (ls, grep, cat) to find it. Work only inside the current directory. When you are done, write ONLY the final answer to the file answer.txt in the current directory."
            expected = "UNSOLVABLE"
        else:
            instruction = f"The directory kb/ contains a small knowledge base of markdown files. In which city is the headquarters of {target_person}'s employer? Use the file tools or bash (ls, grep, cat) to find it. Work only inside the current directory. When you are done, write ONLY the final answer to the file answer.txt in the current directory."
            slug = target_person.lower().replace(" ", "_")
            lines = (kb_dir / f"person_{slug}.md").read_text(encoding="utf-8").splitlines()
            emp = [ln.split(":")[1].strip() for ln in lines if "Employer:" in ln][0]
            expected = company_cities[emp]

    return {
        "task_id": task_id,
        "task_type": "search",
        "instruction": instruction,
        "reward": rng.randint(1, 4),
        "expected": expected,
        "unsolvable": unsolvable
    }


def generate_data_task(task_id: str, task_dir: Path, unsolvable: bool, rng: random.Random) -> dict:
    workspace = task_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    csv_file = workspace / "sales.csv"

    rows_count = rng.choice([25, 50, 100])
    target_prod = rng.choice(PRODUCTS)
    m_start = rng.randint(1, 5)
    m_end = m_start + rng.randint(1, 3)

    fieldnames = ["order_id", "region", "product", "month", "units", "price"]
    if unsolvable:
        # Невыполнимость: удаляем целевую колонку product или units
        fieldnames = ["order_id", "region", "category", "month", "price"]

    rows = []
    total_units = 0
    for i in range(1, rows_count + 1):
        prod = rng.choice(PRODUCTS)
        month = rng.randint(1, 12)
        units = rng.randint(5, 50)
        price = rng.randint(10, 100)
        reg = rng.choice(REGIONS)
        if prod == target_prod and (m_start <= month <= m_end):
            total_units += units
        if unsolvable:
            rows.append({"order_id": i, "region": reg, "category": prod, "month": month, "price": price})
        else:
            rows.append({"order_id": i, "region": reg, "product": prod, "month": month, "units": units, "price": price})

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    instruction = (
        f"The file sales.csv has columns {','.join(fieldnames)} ({rows_count} rows). "
        f"How many units of product '{target_prod}' were sold in months {m_start} through {m_end} inclusive? "
        f"Use bash with python3 to compute it. Work only inside the current directory. "
        f"When you are done, write ONLY the final answer to the file answer.txt in the current directory."
    )

    return {
        "task_id": task_id,
        "task_type": "data_analysis",
        "instruction": instruction,
        "reward": rng.randint(2, 5),
        "expected": "UNSOLVABLE" if unsolvable else str(total_units),
        "unsolvable": unsolvable
    }


def generate_math_task(task_id: str, task_dir: Path, unsolvable: bool, rng: random.Random) -> dict:
    start_boxes = rng.randint(1000, 2500)
    current = start_boxes
    steps = []

    for _ in range(rng.randint(2, 4)):
        op = rng.choice(["split", "double", "ship", "receive"])
        if op == "split":
            k = 0 if unsolvable else rng.choice([2, 3])
            steps.append(f"Then the stock is split equally into {k} warehouses and it keeps one share (rounded down).")
            if k == 0:
                break
            current //= k
        elif op == "double":
            steps.append("Then the stock is doubled by merging with a sister warehouse.")
            current *= 2
        elif op == "ship":
            boxes_day = rng.randint(10, 30)
            days = rng.randint(2, 4)
            steps.append(f"It ships {boxes_day} boxes per day for {days} days.")
            current -= (boxes_day * days)
        elif op == "receive":
            deliv = rng.randint(2, 3)
            each = rng.randint(20, 60)
            steps.append(f"It receives {deliv} deliveries of {each} boxes each.")
            current += (deliv * each)

    instruction = (
        f"A warehouse starts with {start_boxes} boxes. " + " ".join(steps) + " "
        "How many boxes does it have at the end? Compute it with the bash tool (python3 -c). "
        "Work only inside the current directory. When you are done, write ONLY the final answer to the file answer.txt in the current directory."
    )

    return {
        "task_id": task_id,
        "task_type": "math",
        "instruction": instruction,
        "reward": rng.randint(1, 5),
        "expected": "UNSOLVABLE" if unsolvable else str(current),
        "unsolvable": unsolvable
    }


def generate_coding_task(task_id: str, task_dir: Path, unsolvable: bool, rng: random.Random) -> dict:
    workspace = task_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Исходный код с намеренной ошибкой в average или count_even
    buggy_lib = """def reverse_words(s):
    return ' '.join(reversed(s.split()))

def total(xs):
    return sum(xs)

def maximum(xs):
    return max(xs) if xs else 0

def average(xs):
    # BUG: division by len-1
    return sum(xs) / (len(xs) - 1) if len(xs) > 1 else xs[0]

def count_even(xs):
    # BUG: counts odd instead
    return sum(1 for x in xs if x % 2 == 1)
"""
    (workspace / "mylib.py").write_text(buggy_lib, encoding="utf-8")

    if unsolvable:
        # Конфликтующие ассерты: average([2, 4, 6]) должен быть одновременно 4 и 100
        test_content = """import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_total(self):
        self.assertEqual(m.total([1, 2, 3]), 6)

    def test_conflict_a(self):
        self.assertEqual(m.average([2, 4, 6]), 4)

    def test_conflict_b(self):
        self.assertEqual(m.average([2, 4, 6]), 100)

if __name__ == '__main__':
    unittest.main()
"""
    else:
        test_content = """import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_reverse_words(self):
        self.assertEqual(m.reverse_words('c a b'), 'b a c')

    def test_total(self):
        self.assertEqual(m.total([1, 2, 3]), 6)

    def test_average(self):
        self.assertEqual(m.average([2, 4, 6]), 4)

    def test_count_even(self):
        self.assertEqual(m.count_even([1, 2, 4, 6, 7]), 3)

if __name__ == '__main__':
    unittest.main()
"""
    (workspace / "test_mylib.py").write_text(test_content, encoding="utf-8")

    instruction = (
        "Run `python3 test_mylib.py` in the current directory; some tests fail. "
        "Fix the bugs in mylib.py (do not edit the tests) until all tests pass. "
        "Work only inside the current directory. When you are done, write ONLY the word DONE to the file answer.txt in the current directory."
    )

    return {
        "task_id": task_id,
        "task_type": "coding",
        "instruction": instruction,
        "reward": rng.randint(2, 6),
        "expected": "UNSOLVABLE" if unsolvable else "DONE",
        "unsolvable": unsolvable
    }


def generate_pool(out_dir: Path, total: int = 40, seed: int = 42) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    types = ["coding", "data_analysis", "math", "search"]
    per_type = total // len(types)

    index = 0
    all_tasks = []

    for ttype in types:
        for _ in range(per_type):
            index += 1
            tid = f"{ttype}_{index:04d}"
            tdir = out_dir / tid
            tdir.mkdir(parents=True, exist_ok=True)
            # 20% невыполнимых задач
            unsolvable = (index % 5 == 0)

            if ttype == "search":
                meta = generate_search_task(tid, tdir, unsolvable, rng)
            elif ttype == "data_analysis":
                meta = generate_data_task(tid, tdir, unsolvable, rng)
            elif ttype == "math":
                meta = generate_math_task(tid, tdir, unsolvable, rng)
            elif ttype == "coding":
                meta = generate_coding_task(tid, tdir, unsolvable, rng)

            (tdir / "task.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            all_tasks.append(meta)

    print(f"Успешно создано {len(all_tasks)} задач в {out_dir}:")
    print(f"- Выполнимых: {sum(1 for t in all_tasks if not t['unsolvable'])}")
    print(f"- Невыполнимых (20%): {sum(1 for t in all_tasks if t['unsolvable'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("./synthetic_dev_pool"))
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate_pool(args.out_dir, args.count, args.seed)