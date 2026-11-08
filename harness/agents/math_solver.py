"""Солвер для математических и текстовых алгоритмических задач (math)."""
import re

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model
from harness.sandbox.executor import run_python_snippet


def _try_warehouse_math_zero_token(instruction: str) -> str | None:
    """
    Детерминированный парсер для последовательных операций со складом из примеров math_0000 / math_0004.
    """
    m_start = re.search(r"starts with (\d+) boxes\.", instruction)
    if not m_start:
        return None
    boxes = int(m_start.group(1))
    sentences = [s.strip() for s in instruction.split(".") if s.strip()]
    for sent in sentences[1:]:
        if sent.startswith("How many boxes") or sent.startswith("Compute it") or sent.startswith("Work only") or sent.startswith("When you are done"):
            continue
        m_split = re.search(r"split equally into (\d+) warehouses and it keeps one share \(rounded down\)", sent)
        if m_split:
            k = int(m_split.group(1))
            if k <= 0:
                return "UNSOLVABLE"
            boxes //= k
            continue
        if "stock is doubled by merging with a sister warehouse" in sent:
            boxes *= 2
            continue
        m_ship = re.search(r"ships (\d+) boxes per day for (\d+) days", sent)
        if m_ship:
            boxes -= int(m_ship.group(1)) * int(m_ship.group(2))
            continue
        m_rec = re.search(r"receives (\d+) deliveries of (\d+) boxes each", sent)
        if m_rec:
            boxes += int(m_rec.group(1)) * int(m_rec.group(2))
            continue
        # Если встретилась незнакомая фраза — отдаём задачу модели
        return None
    return str(boxes)


async def solve_math_task(ctx: TaskContext, bridge) -> SolveResult:
    fast = _try_warehouse_math_zero_token(ctx.instruction)
    if fast == "UNSOLVABLE":
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Division by zero")
    if fast is not None:
        return SolveResult(
            task_id=ctx.task_id,
            status="SOLVED",
            answer=fast,
            notes="Solved zero-token via rule parser",
        )

    model = select_primary_model(ctx)
    sys_prompt = (
        "Translate the math word problem into a short Python 3 script that computes and prints ONLY the final integer answer. "
        "If the problem is contradictory or impossible, print UNSOLVABLE. Output ONLY raw Python code without markdown."
    )
    code_resp, in_tok, out_tok, r_tok = await bridge.complete(
        model=model, system_prompt=sys_prompt, user_prompt=ctx.instruction, max_tokens=200
    )
    clean_code = re.sub(r"^```(?:python)?|```$", "", code_resp.strip(), flags=re.MULTILINE).strip()
    ok, stdout, err = run_python_snippet(clean_code, cwd=ctx.workspace_dir)
    if ok and stdout.strip():
        ans = stdout.strip().splitlines()[-1].strip()
        if "UNSOLVABLE" in ans.upper():
            return SolveResult(
                task_id=ctx.task_id,
                status="UNSOLVABLE",
                input_tokens=in_tok,
                output_tokens=out_tok,
                reasoning_tokens=r_tok,
                model_used=model,
            )
        return SolveResult(
            task_id=ctx.task_id,
            status="SOLVED",
            answer=ans,
            input_tokens=in_tok,
            output_tokens=out_tok,
            reasoning_tokens=r_tok,
            model_used=model,
        )

    return SolveResult(
        task_id=ctx.task_id,
        status="FAILED",
        input_tokens=in_tok,
        output_tokens=out_tok,
        reasoning_tokens=r_tok,
        model_used=model,
        notes=err[:200],
    )
