"""Experimental local execution of instructions fully parsed by the v2 grammar."""
import csv
from harness.config import SolveResult
from harness.agents.join_scope_v2 import parse_join_scope_v2, join_scope_v2_route
from harness.agents.join_plans import execute_join_plan
from harness.agents.multi_csv import select_csv_inputs, solve_multi_csv_task


def local_join_route(workspace, instruction):
    return 'local' if join_scope_v2_route(workspace, instruction) == 'json_plan' else 'python'


async def solve_local_join_task(ctx, bridge):
    if local_join_route(ctx.workspace_dir, ctx.instruction) != 'local':
        return await solve_multi_csv_task(ctx, bridge)
    plan = parse_join_scope_v2(ctx.instruction)
    selected = select_csv_inputs(ctx.workspace_dir, ctx.instruction)
    try:
        answer = execute_join_plan(plan, selected)
    except (OSError, UnicodeError, csv.Error, ValueError, TypeError, KeyError, OverflowError) as error:
        # Do not spend tokens to retry an invalid local computation.
        return SolveResult(task_id=ctx.task_id, status='UNKNOWN', model_used='',
                           notes='Local typed join rejected: ' + type(error).__name__)
    return SolveResult(task_id=ctx.task_id, status='SOLVED', answer=answer, model_used='',
                       notes='Executed complete bounded grammar locally; no model translation')
