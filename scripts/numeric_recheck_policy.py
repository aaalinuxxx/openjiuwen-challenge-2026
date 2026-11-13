"""Experimental numeric-literal signal and a single computation request."""
import ast,math,re
from decimal import Decimal,InvalidOperation
from harness.config import SolveResult,MODEL_QWEN_27B_NOREASON
from harness.agents.base_harness import OpenJiuwenLLMBridge,TruncatedGeneration
from harness.planner.budget_tracker import BudgetDenied
from harness.sandbox.executor import run_python_snippet
from terse_math_benchmark import BASELINE_MATH_PROMPT
CALCULATION_PROMPT=BASELINE_MATH_PROMPT+(
    ' Compute the result from the numbers in the task with Python operations. '
    'Do not replace the calculation with a precomputed numeric constant. Keep code concise, without comments.'
)
def clean_code(code):
    return re.sub(r'^\x60\x60\x60(?:python)?\s*|\x60\x60\x60$', '', code.strip(), flags=re.MULTILINE).strip()
def numeric_literal_only(code):
    """Narrow syntactic signal; False does NOT mean mathematically verified."""
    try:body=ast.parse(clean_code(code)).body
    except (SyntaxError,ValueError):return False
    if len(body)>1 and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):body=body[1:]
    names={}
    def literal(node):
        if isinstance(node,ast.Name):return names.get(node.id,False)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):return literal(node.operand)
        if not isinstance(node,ast.Constant) or isinstance(node.value,bool):return False
        if isinstance(node.value,(int,float)):
            return not isinstance(node.value,float) or math.isfinite(node.value)
        if isinstance(node.value,str):
            try:return Decimal(node.value).is_finite()
            except InvalidOperation:return False
        return False
    if not body:return False
    for stmt in body[:-1]:
        if not isinstance(stmt,ast.Assign) or len(stmt.targets)!=1 or not isinstance(stmt.targets[0],ast.Name) or not literal(stmt.value):return False
        names[stmt.targets[0].id]=True
    last=body[-1]
    if not isinstance(last,ast.Expr):return False
    value=last.value
    if isinstance(value,ast.Call):
        return (isinstance(value.func,ast.Name) and value.func.id=='print' and len(value.args)==1 and not value.keywords and literal(value.args[0]))
    return literal(value)

async def calculate_again(ctx,config,tracker):
    bridge=OpenJiuwenLLMBridge(config,tracker,ctx)
    try:
        code,*_=await bridge.complete(MODEL_QWEN_27B_NOREASON,CALCULATION_PROMPT,ctx.instruction,max_tokens=200)
        if numeric_literal_only(code):
            result=SolveResult(ctx.task_id,'UNKNOWN',notes='Numeric literal still unverified after one computation request')
        else:
            ok,stdout,error=run_python_snippet(clean_code(code),ctx.workspace_dir)
            answer=stdout.strip().splitlines()[-1].strip() if stdout.strip() else None
            if ok and answer and 'UNSOLVABLE' in answer.upper():result=SolveResult(ctx.task_id,'UNSOLVABLE')
            elif ok and answer:result=SolveResult(ctx.task_id,'SOLVED',answer=answer)
            else:result=SolveResult(ctx.task_id,'FAILED',notes=error[:200] or 'No stdout')
    except TruncatedGeneration:
        result=SolveResult(ctx.task_id,'TRUNCATED',notes='Correction output truncated; no retry')
    except BudgetDenied as exc:
        result=SolveResult(ctx.task_id,'BUDGET_EXCEEDED',notes=str(exc))
    except Exception as exc:
        result=SolveResult(ctx.task_id,'ACCOUNTING_UNKNOWN' if tracker.has_unaccounted_request else 'FAILED',notes=type(exc).__name__)
    result.input_tokens,result.output_tokens,result.reasoning_tokens=tracker.usage_for_task(ctx.task_id)
    result.model_used=bridge.last_attempted_model
    return result
