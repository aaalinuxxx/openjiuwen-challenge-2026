"""Diagnostic: one real corrective call for each frozen historical literal case.

Initial responses are replay evidence, not new generation calls. Labels are read
only after all policy decisions. This does not measure end-to-end ranking gain.
"""
import argparse,asyncio,hashlib,json,sys,tempfile,time,shutil
from dataclasses import asdict
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from api_settings import load_settings
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.workflow_runner import task_runner
from numeric_recheck_policy import calculate_again,numeric_literal_only

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
async def run(args):
    planpath=args.plan.resolve();plan=read(planpath)
    for name,sha in plan['frozen_hashes'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen input changed: '+name)
    cases=read(ROOT/plan['cases'])
    for case in cases:
        for key in ('request','response','report'):
            if digest(ROOT/case['source_'+key])!=case[key+'_sha256']:raise ValueError('Historical evidence changed')
        if not numeric_literal_only(case['initial_code']):raise ValueError('Selected case is not covered by signal')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/(plan['output_prefix']+('_live_' if args.live else '_offline_')+stamp)
    if args.live:
        with planpath.with_name(planpath.stem+'_started.json').open('x',encoding='utf-8') as f:json.dump(dict(directory=directory.name,plan_sha256=digest(planpath)),f)
    directory.mkdir(parents=True);print('Report:',directory/'report.json',flush=True)
    report=dict(status='RUNNING',mode='LIVE_CORRECTION_DIAGNOSTIC' if args.live else 'OFFLINE_ZERO_BUDGET',plan_sha256=digest(planpath),hypothesis=plan['hypothesis'])
    write(directory/'report.json',report)
    settings=load_settings() if args.live else {'LLM_BASE_URL':'https://fixture.invalid/v1','LLM_API_KEY':'offline'}
    tracker=BudgetTracker(plan['budget'] if args.live else 0,audit_path=directory/'budget.json',max_requests=plan['max_calls'] if args.live else 0)
    sent=0;results=[];original=OpenJiuwenLLMBridge._get_transport
    def recording(bridge):
        if not args.live:raise AssertionError('Offline transport forbidden')
        transport=original(bridge)
        async def send(payload):
            nonlocal sent
            sent+=1;i=sent;write(directory/f'request_{i:02d}.json',dict(task_id=bridge.task_id,payload=payload))
            raw=await transport(payload)
            write(directory/f'response_{i:02d}.json',dict(task_id=bridge.task_id,response=raw));return raw
        return send
    async def correction_solver(ctx,config,budget_tracker=None):return await calculate_again(ctx,config,budget_tracker)
    with tempfile.TemporaryDirectory(prefix='oj-literal-') as temp:
        tasks=Path(temp)
        config=HarnessConfig(tasks,None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],max_concurrency=1,initial_budget_tokens=plan['budget'] if args.live else 0,execution_engine='openjiuwen')
        runner=task_runner(config,tracker)
        try:
            with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording),patch('harness.workflow_runner.solve_task',correction_solver):
                for case in cases:
                    root=tasks/case['case_id'];root.mkdir()
                    write(root/'task.json',dict(task_id=case['case_id'],task_type='math',instruction=case['instruction'],reward=1))
                    ctx=TaskContext(case['case_id'],'math',case['instruction'],1,root,root,plan['per_case_budget'],False)
                    result=await runner.run(ctx)
                    results.append(dict(case_id=case['case_id'],result=asdict(result)))
                    write(directory/'progress.json',dict(results=results,budget=tracker.snapshot()))
                    print(json.dumps(dict(case_id=case['case_id'],status=result.status,cost=result.effective_cost)),flush=True)
                    if tracker.proxy_exhausted or tracker.has_unaccounted_request:break
            labels=read(ROOT/plan['labels']);rows=[]
            indexed={r['case_id']:r['result'] for r in results}
            for case in cases:
                id=case['case_id'];result=indexed.get(id,{'status':'NOT_RUN'});root=tasks/id;answerfile=root/'answer.txt'
                answer=answerfile.read_text(encoding='utf-8').strip() if answerfile.exists() else None
                try:match=answer is not None and Decimal(answer).is_finite() and Decimal(answer)==Decimal(labels[id]['expected'])
                except InvalidOperation:match=False
                expected_public=dict(task_id=id,task_type='math',instruction=case['instruction'],reward=1)
                integrity=(not root.exists() or (read(root/'task.json')==expected_public and not any(p.name not in ('task.json','answer.txt') for p in root.iterdir())))
                correct=bool(match and result['status']=='SOLVED' and integrity)
                rows.append(dict(case_id=id,task_id=case['task_id'],expected=labels[id]['expected'],baseline_correct=labels[id]['baseline_correct'],answer=answer,integrity_passed=integrity,verified_solution=correct,incorrect_solved=result['status']=='SOLVED' and not match,result=result))
            baseline=sum(r['baseline_correct'] for r in rows);correct=sum(r['verified_solution'] for r in rows)
            cost=Decimal(0);checks=[];events=[e for e in tracker.events if e['status']!='NOT_SENT'];responses=sorted(directory.glob('response_*.json'));requests=sorted(directory.glob('request_*.json'))
            checks.append(len(events)==len(responses)==len(requests)==sent)
            for qpath,rpath,event in zip(requests,responses,events):
                q=read(qpath);r=read(rpath);u=r['response']['usage'];delta=Decimal(u['prompt_tokens'])/10+u['completion_tokens'];cost+=delta
                checks.append(q['task_id']==r['task_id']==event['task_id'] and event['status']=='ACCOUNTED' and event['input_tokens']==u['prompt_tokens'] and event['output_tokens']==u['completion_tokens'] and Decimal(str(event['effective_cost']))==delta and event['output_cap']==q['payload']['max_tokens'] and r['response']['model']==q['payload']['model'] and u['total_tokens']==u['prompt_tokens']+u['completion_tokens'] and not u.get('completion_tokens_details',{}).get('reasoning_tokens',0))
            checks.extend([not tracker.has_unaccounted_request,not tracker.proxy_exhausted,tracker.reserved_effective_tokens==0,abs(float(cost)-tracker.spent_effective_tokens)<1e-7,float(cost)<=plan['budget'],sent<=plan['max_calls']])
            history=sum(Decimal(c['initial_usage']['prompt_tokens'])/10+c['initial_usage']['completion_tokens'] for c in cases)
            lost=[r['case_id'] for r in rows if r['baseline_correct'] and not r['verified_solution']];gained=[r['case_id'] for r in rows if not r['baseline_correct'] and r['verified_solution']]
            report.update(rows=rows,metrics=dict(cases=len(rows),unique_instructions=len({c['instruction'] for c in cases}),baseline_correct=baseline,correct=correct,input_integrity=all(r['integrity_passed'] for r in rows),non_solved_answer_files=sum(r['answer'] is not None and r['result']['status']!='SOLVED' for r in rows),wrong_solved=sum(r['incorrect_solved'] for r in rows),lost_controls=lost,recovered_cases=gained),audit=dict(passed=all(checks),new_accounted_calls=len(responses),new_effective_tokens=float(cost)),historical_initial_effective_tokens=float(history),policy_cost_including_historical_initials=float(history+cost),workflow_runs=runner.runs)
            report['accepted_diagnostic']=bool(args.live and all(checks) and not lost and not report['metrics']['wrong_solved'] and report['metrics']['input_integrity'] and not report['metrics']['non_solved_answer_files'] and correct>=baseline+2)
            report['status']='COMPLETED' if all(checks) else 'STOPPED_ACCOUNTING_OR_RECORDING'
        finally:
            report.update(actual_transport_attempts=sent,budget=tracker.snapshot(),frozen_files_unchanged=all(digest(ROOT/n)==sha for n,sha in plan['frozen_hashes'].items()))
            shutil.copytree(tasks,directory/'task_artifacts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));write(directory/'report.json',report)
    print(json.dumps({k:report.get(k) for k in ('status','metrics','audit','accepted_diagnostic')}),flush=True)
    return 0 if report['status']=='COMPLETED' and report['frozen_files_unchanged'] else 1
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
