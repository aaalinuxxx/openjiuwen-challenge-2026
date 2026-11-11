"""Experimental cascade: fallback only after an explicit join-plan UNSUPPORTED."""
from harness.agents.join_plans import solve_join_plan_task
from harness.agents.multi_csv import solve_multi_csv_task


async def solve_join_cascade_task(ctx, bridge):
    first = await solve_join_plan_task(ctx, bridge)
    if first.status != "UNKNOWN" or first.notes != "Model declared unsupported conditions":
        return first
    # Keep the SAME context and bridge: the second reserve sees the first
    # request's actual usage, task cap, global cap and uncertain-cost stop.
    second = await solve_multi_csv_task(ctx, bridge)
    second.input_tokens += first.input_tokens
    second.output_tokens += first.output_tokens
    second.reasoning_tokens += first.reasoning_tokens
    second.notes = "Join cascade: Python after explicit UNSUPPORTED. " + second.notes
    return second
