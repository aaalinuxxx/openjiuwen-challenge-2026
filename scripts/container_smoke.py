"""Offline delivery-contract check: real SDK, four domains, no paid API calls.

Default: test a previously built Docker image with the competition restrictions.
--python PATH: check the same fixtures in a host interpreter (not a Docker test).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def make_fixtures(tasks):
    cases = {
        "math_local": ("math", True,
            "A warehouse starts with 100 boxes. It ships 3 boxes per day for 4 days. "
            "How many boxes does it have at the end? Write only the final answer to answer.txt.", {}, "88"),
        "search_local": ("search", True,
            "In which year was Alba born? Write only the final answer to answer.txt.",
            {"kb/alba.md": "# Alba\nborn: 1987\n"}, "1987"),
        "csv_local": ("data_analysis", False,
            "How many units of product 'widget' were sold in months 5 through 6 inclusive? "
            "Write only the final answer to answer.txt.",
            {"sales.csv": "product,month,units\nwidget,5,4\nwidget,6,5\nwidget,7,80\n"}, "9"),
        "coding_local": ("coding", True,
            "Run the tests, preserve code if they pass, then write DONE to answer.txt.", {
                "mylib.py": "def f(x):\n    return x + 1\n",
                "test_mylib.py": "import unittest\nfrom mylib import f\nclass T(unittest.TestCase):\n"
                    "    def test_f(self): self.assertEqual(f(4), 5)\n"
                    "if __name__ == '__main__': unittest.main()\n",
            }, "DONE"),
        "missing_data": ("data_analysis", False,
            "Read absent.csv and sum qty. Do not invent unavailable input.", {}, None),
    }
    for name, (kind, nested, instruction, files, _) in cases.items():
        task = tasks / name
        task.mkdir(parents=True)
        (task / "task.json").write_text(json.dumps(dict(
            task_id=name, task_type=kind, instruction=instruction, reward=1)), encoding="utf-8")
        work = task / "workspace" if nested else task
        work.mkdir(exist_ok=True)
        for filename, content in files.items():
            path = work / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return cases


def fingerprints(tasks):
    return {p.relative_to(tasks).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tasks.rglob("*") if p.is_file()}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="hack:latest")
    parser.add_argument("--python", help="Host interpreter; does not test container isolation")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="oj-smoke-") as temporary:
        base = Path(temporary)
        tasks, output, logs = base / "tasks", base / "out", base / "logs"
        output.mkdir()
        logs.mkdir()
        cases = make_fixtures(tasks)
        before = fingerprints(tasks)
        # Fixtures only: a capability-free container must be able to write them.
        for path in [base, *base.rglob("*")]:
            path.chmod(0o777 if path.is_dir() else 0o666)
        env = dict(os.environ)
        if args.python:
            env.update(BUDGET="0", LLM_BASE_URL="http://127.0.0.1:1/v1",
                       LLM_API_KEY="offline-fixture", OUT=str(output),
                       TMPDIR=str(logs), TMP=str(logs), TEMP=str(logs),
                       PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            command = [args.python, "-B", str(ROOT / "run_agent.py"), "--tasks-dir", str(tasks)]
            mode = "host (not a Docker test)"
        else:
            size = int(subprocess.check_output(
                ["docker", "image", "inspect", args.image, "--format", "{{.Size}}"], text=True))
            require(size < 4_000_000_000, f"Image exceeds 4 GB: {size} bytes")
            command = ["docker", "run", "--rm", "--network", "none",
                "--read-only", "--tmpfs", "/tmp:rw,size=2g",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--cpus", "4", "--memory", "16g", "--pids-limit", "512",
                "-e", "HOME=/tmp", "-e", "BUDGET=0", "-e", "OUT=/data/out",
                "-e", "LLM_BASE_URL=http://127.0.0.1:1/v1", "-e", "LLM_API_KEY=offline-fixture",
                "-v", f"{tasks}:/data/tasks:rw", "-v", f"{output}:/data/out:rw",
                "-v", f"{logs}:/tmp/openjiuwen_logs:rw",
                "--workdir", "/app", "--entrypoint", "python", args.image,
                "/app/run_agent.py", "--tasks-dir", "/data/tasks"]
            mode = "Docker: read-only, network none, 4 CPUs"
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=180)
        expected = {}
        for name, (_, nested, _, _, answer) in cases.items():
            paths = [tasks / name / "answer.txt"]
            if nested:
                paths.append(tasks / name / "workspace" / "answer.txt")
            for path in paths:
                actual = path.read_text(encoding="utf-8").strip() if path.exists() else None
                require(actual == answer, f"Wrong answer at {path}: {actual!r}")
            if answer is not None:
                expected[name] = answer
        require(json.loads((output / "solutions.json").read_text()) == expected, "OUT mismatch")
        after = fingerprints(tasks)
        require(all(after.get(name) == digest for name, digest in before.items()), "Input changed")
        require(all(name in before or name.endswith("/answer.txt") for name in after), "Unexpected output")
        ledgers = [json.loads(p.read_text()) for p in logs.rglob("budget_*.json")]
        require(len(ledgers) == 1 and ledgers[0]["budget"] == 0 and not ledgers[0]["events"],
                "Expected a zero-budget ledger with no HTTP attempts")
        print(json.dumps(dict(passed=True, mode=mode, solved=4, missing_data_skipped=True,
                              inputs_unchanged=True, aggregate_out=True, http_attempts=0)))


if __name__ == "__main__":
    main()
