"""Солвер для математических и текстовых алгоритмических задач (math)."""
import re

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model
from harness.sandbox.executor import run_python_snippet


def _try_warehouse_math_zero_token(instruction: str) -> str | None:
    """Fully parse operations before evaluating a typed arithmetic plan."""
    from harness.agents.calculation_plans import parse_warehouse_plan, execute_warehouse_plan
    plan = parse_warehouse_plan(instruction)
    return None if plan is None else execute_warehouse_plan(plan)


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
