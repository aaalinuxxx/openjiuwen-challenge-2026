"""Task orchestration with the pinned openJiuwen workflow engine.

Secrets and mutable budget state stay in closures, never in SDK inputs/state.
The direct runner is an explicit diagnostic mode, never an automatic fallback.
"""
from dataclasses import asdict
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from harness.config import SolveResult
from harness.agents.base_harness import solve_task
from harness.sandbox.file_guard import save_task_answer


class SDKUnavailable(RuntimeError):
    pass


def load_sdk():
    if not (3,11) <= sys.version_info[:2] < (3,14):
        raise SDKUnavailable('openjiuwen==0.1.19 needs Python 3.11–3.13; use the SDK environment or Docker')
    try:
        installed=version('openjiuwen')
    except PackageNotFoundError:
        raise SDKUnavailable('Install requirements.txt in Python 3.11–3.13; openjiuwen is missing') from None
    if installed!='0.1.19':
        raise SDKUnavailable('Expected openjiuwen==0.1.19, found '+installed)
    from openjiuwen.core.common.logging.log_config import configure_log_config
    configure_log_config(dict(backend='default',level='WARNING',
        log_path=str(Path(tempfile.gettempdir())/'openjiuwen_logs'/'sdk'),
        output=['console'],interface_output=['console'],performance_output=['console']))
    import openjiuwen.core.workflow as sdk
    return sdk


def finalize(ctx, result, config):
    if result.task_id!=ctx.task_id:
        raise ValueError('Result belongs to a different task')
    saved=result.status=='SOLVED' and result.answer is not None
    if saved:
        save_task_answer(ctx.task_dir,ctx.workspace_dir,ctx.task_id,result.answer,config.out_path)
    return saved


class DirectTaskRunner:
    def __init__(self,config,tracker):
        self.config,self.tracker=config,tracker
        self.runs=[]

    async def run(self,ctx):
        result=await solve_task(ctx,self.config,budget_tracker=self.tracker)
        finalize(ctx,result,self.config)
        return result


class OpenJiuwenTaskRunner:
    def __init__(self,config,tracker):
        self.sdk=load_sdk()
        self.config,self.tracker=config,tracker
        self.runs=[]

    async def run(self,ctx):
        sdk=self.sdk
        from openjiuwen.core.session.constants import WORKFLOW_EXECUTE_TIMEOUT
        trace=dict(task_id=ctx.task_id,workflow_id='task_'+uuid4().hex,session_id=uuid4().hex,
                   stages=[],saved=False,state='STARTED')
        trace.update(request_timeout_sec=self.config.request_timeout_sec,
                     workflow_timeout_sec=self.config.workflow_timeout_sec)
        self.runs.append(trace)
        owner=self

        class Solve(sdk.WorkflowComponent):
            async def invoke(self,inputs,session,context):
                if inputs['task_id']!=ctx.task_id: raise ValueError('Workflow task mismatch')
                trace['stages'].append('solve')
                result=await solve_task(ctx,owner.config,budget_tracker=owner.tracker)
                return {'result':asdict(result)}

        class Finalize(sdk.WorkflowComponent):
            async def invoke(self,inputs,session,context):
                trace['stages'].append('finalize')
                result=SolveResult(**inputs['result'])
                trace['saved']=finalize(ctx,result,owner.config)
                return {'result':asdict(result),'saved':trace['saved']}

        flow=sdk.Workflow(card=sdk.WorkflowCard(id=trace['workflow_id'],name='budgeted_task',version='1',
            input_params={'type':'object','properties':{'task_id':{'type':'string'}},'required':['task_id']}))
        flow.set_start_comp('start',sdk.Start(),inputs_schema={'task_id':'${task_id}'})
        flow.add_workflow_comp('solve',Solve(),inputs_schema={'task_id':'${start.task_id}'},max_retries=0)
        flow.add_workflow_comp('finalize',Finalize(),inputs_schema={'result':'${solve.result}'},max_retries=0)
        flow.set_end_comp('end',sdk.End(),inputs_schema={'result':'${finalize.result}','saved':'${finalize.saved}'})
        flow.add_connection('start','solve')
        flow.add_connection('solve','finalize')
        flow.add_connection('finalize','end')
        try:
            output=await flow.invoke({'task_id':ctx.task_id},sdk.create_workflow_session(session_id=trace['session_id'],
                envs={WORKFLOW_EXECUTE_TIMEOUT: self.config.workflow_timeout_sec}))
            if output.state!=sdk.WorkflowExecutionState.COMPLETED:
                raise RuntimeError('Workflow did not complete')
            result=SolveResult(**output.result['output']['result'])
            if result.task_id!=ctx.task_id or trace['stages']!=['solve','finalize']:
                raise RuntimeError('Workflow execution contract failed')
            trace['state']='COMPLETED'
            return result
        except Exception as exc:
            trace.update(state='FAILED',error_type=type(exc).__name__)
            counts=self.tracker.usage_for_task(ctx.task_id)
            return SolveResult(task_id=ctx.task_id,status='WORKFLOW_FAILED',
                               input_tokens=counts[0],output_tokens=counts[1],reasoning_tokens=counts[2],
                               notes=type(exc).__name__)


def task_runner(config,tracker):
    if config.execution_engine=='openjiuwen': return OpenJiuwenTaskRunner(config,tracker)
    if config.execution_engine=='direct': return DirectTaskRunner(config,tracker)
    raise ValueError('Unknown execution engine')
