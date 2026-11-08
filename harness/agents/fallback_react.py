"""Резервный агент для нестандартных категорий задач."""
from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model


async def solve_fallback_task(ctx: TaskContext, bridge) -> SolveResult:
    model = select_primary_model(ctx)
    sys_prompt = (
        "Solve the task concisely. Output ONLY the exact final string or number to be written to answer.txt. "
        "If the task is impossible, output UNSOLVABLE."
    )
    resp, in_tok, out_tok, r_tok = await bridge.complete(
        model=model, system_prompt=sys_prompt, user_prompt=ctx.instruction, max_tokens=128
    )
    ans = resp.strip().splitlines()[-1].strip() if resp.strip() else ""
    if not ans or "UNSOLVABLE" in ans.upper():
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
