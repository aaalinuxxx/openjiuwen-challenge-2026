"""H04.18/E83-E84: paired SDK data benchmark. Default offline; --live uses real API."""
import argparse
import asyncio
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'experiments/E83_output_contract'
TASKS=ROOT/'experiments/E77_mixed_integration/tasks'
LABELS=ROOT/'experiments/E77_mixed_integration/labels.json'
E80=ROOT/'experiments/E80_allocation_live_20261111T202642547670/candidate'

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def hashes(root):
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
def truths():
    return {n:t for n,t in json.loads(LABELS.read_text(encoding='utf-8')).items() if t['task_type']=='data_analysis'}
def grade(n,t,result,root,before):
    p=root/'answer.txt';answer=p.read_text(encoding='utf-8').strip() if p.is_file() else None
    after=hashes(root)
    integrity=all(after.get(n)==sha for n,sha in before.items()) and not(set(after)-set(before)-{'answer.txt'})
    match=answer is not None and answer==str(t['expected'])
    if t['group']=='E75_pilot' and answer is not None:
        try: match=Decimal(answer).is_finite() and Decimal(answer)==Decimal(t['expected'])
        except InvalidOperation: match=False
    status=result.get('status','NOT_RUN')
    verified=bool(not t['unsolvable'] and match and status=='SOLVED' and integrity)
    return dict(task_id=n,group=t['group'],expected=t['expected'],unsolvable=t['unsolvable'],
        status=status,answer=answer,verified=verified,integrity=bool(integrity),
        unverified_answer_file=answer is not None and not verified,
        non_solved_answer_file=answer is not None and status!='SOLVED',
        incorrect_solved_answer=status=='SOLVED' and not match,result=result)
def metrics(rows):
    return dict(total=len(rows),solvable=sum(not r['unsolvable'] for r in rows),verified=sum(r['verified'] for r in rows),
        non_solved_answer_files=sum(r['non_solved_answer_file'] for r in rows),
        incorrect_solved_answers=sum(r['incorrect_solved_answer'] for r in rows),
        unverified_answer_files=sum(r['unverified_answer_file'] for r in rows),
        integrity_passed=all(r['integrity'] for r in rows))

async def worker(args):
    source=args.source.resolve();sys.path.insert(0,str(source))
    from dataclasses import asdict
    from api_settings import load_settings
    from harness.config import HarnessConfig,TaskContext
    from harness.agents.multi_csv import solve_multi_csv_task
    from harness.agents.base_harness import OpenJiuwenLLMBridge
    from harness.planner.scheduler import TaskScheduler
    from harness.workflow_runner import finalize
    plan=json.loads((DESIGN/'live_plan.json').read_text(encoding='utf-8'))
    expected=plan['baseline_hashes'] if args.arm=='baseline' else plan['candidate_harness_hashes']
    for n,sha in expected.items():
        if digest(source/n)!=sha: raise ValueError('Harness differs from frozen plan: '+n)
    output=args.output;output.mkdir(parents=True);labels=truths()
    with tempfile.TemporaryDirectory(prefix='oj-contract-tasks-') as temp:
        taskroot=Path(temp)/'tasks';taskroot.mkdir()
        for n in labels: shutil.copytree(TASKS/n,taskroot/n)
        initial={n:hashes(taskroot/n) for n in labels}
        settings=load_settings() if args.mode=='live' else dict(LLM_BASE_URL='https://fixture.invalid/v1',LLM_API_KEY='offline')
        cfg=HarnessConfig(taskroot,None,settings['LLM_BASE_URL'],settings['LLM_API_KEY'],
            max_concurrency=1,initial_budget_tokens=plan['budget_per_arm'] if args.mode=='live' else 0,
            max_api_calls=plan['max_calls_per_arm'] if args.mode=='live' else 0,
            data_min_task_budget=700,experimental_joins=True,budget_audit_path=output/'budget.json')
        if args.mode=='replay':
            rows=[]
            for path in sorted(E80.glob('response_*.json')):
                recorded=json.loads(path.read_text(encoding='utf-8'));n=recorded['task_id']
                if n not in labels: continue
                code=recorded['response']['choices'][0]['message']['content']
                class ReplayBridge:
                    async def complete(self,**kwargs): return code,0,0,0
                t=labels[n];ctx=TaskContext(n,'data_analysis',t['instruction'],t['reward'],taskroot/n,taskroot/n,700,False)
                result=await solve_multi_csv_task(ctx,ReplayBridge());finalize(ctx,result,cfg)
                row=grade(n,t,asdict(result),taskroot/n,initial[n]);row.update(response_source=path.relative_to(ROOT).as_posix(),response_sha256=digest(path));rows.append(row)
            report=dict(mode='SAVED_PROGRAM_REPLAY_NOT_API',rows=rows,metrics=metrics(rows),actual_http_calls=0,effective_tokens=0,has_unaccounted_request=False,remote_stopped=False)
        else:
            requests=0;recording_errors=[];original=OpenJiuwenLLMBridge._get_transport
            def recording_transport(bridge):
                if args.mode!='live': raise AssertionError('HTTP forbidden during offline rehearsal')
                transport=original(bridge)
                async def send(payload):
                    nonlocal requests
                    requests+=1;idx=requests
                    write(output/f'request_{idx:02d}.json',dict(task_id=bridge.task_id,payload=payload))
                    response=await transport(payload)
                    try: write(output/f'response_{idx:02d}.json',dict(task_id=bridge.task_id,response=response))
                    except OSError: recording_errors.append(idx)
                    return response
                return send
            class RecordingScheduler(TaskScheduler):
                async def _run_single(self,item):
                    result=await super()._run_single(item)
                    write(output/'progress.json',dict(results=self.results,budget=self.budget_tracker.snapshot()))
                    print(json.dumps(dict(arm=args.arm,task_id=result.task_id,status=result.status,cost=result.effective_cost)),flush=True)
                    return result
            scheduler=RecordingScheduler(cfg)
            write(output/'ranking.json',[{k:r[k] for k in ('task_id','roi','expected_cost','reward')} for r in scheduler.discover_and_rank_tasks()])
            with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording_transport): summary=await scheduler.run_all()
            rows=[grade(n,t,summary['task_results'].get(n,dict(status='SKIPPED')),taskroot/n,initial[n]) for n,t in labels.items()]
            report=dict(mode=args.mode.upper(),rows=rows,metrics=metrics(rows),summary=summary,actual_http_calls=requests,
                effective_tokens=summary['effective_tokens_spent'],has_unaccounted_request=summary['budget_state']['has_unaccounted_request'],
                remote_stopped=summary['budget_state']['remote_stopped'],recording_errors=recording_errors)
        report.update(arm=args.arm,sources_sha256=expected)
        write(output/'report.json',report)
        shutil.copytree(taskroot,output/'task_artifacts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        print(json.dumps(dict(arm=args.arm,metrics=report['metrics'],calls=report['actual_http_calls'])),flush=True)

def run(args):
    plan=json.loads((DESIGN/'live_plan.json').read_text(encoding='utf-8'))
    for n,sha in plan['frozen_hashes'].items():
        if digest(ROOT/n)!=sha: raise ValueError('Frozen source changed: '+n)
    mode='live' if args.live else 'replay' if args.replay else 'offline'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    output=ROOT/'experiments'/f'E84_contract_{mode}_{stamp}';output.mkdir()
    report=dict(mode=mode.upper(),status='RUNNING',plan_sha256=digest(DESIGN/'live_plan.json'),arms={},real_api_attempts=0,known_effective_tokens=0)
    write(output/'report.json',report)
    if args.live:
        from api_settings import load_settings
        try: load_settings()
        except ValueError:
            report['status']='BLOCKED_API_SETTINGS';write(output/'report.json',report);print('Missing API settings; zero HTTP. Report:',output/'report.json');return 2
        with (DESIGN/'live_started.json').open('x',encoding='utf-8') as f: json.dump(dict(directory=output.name,plan_sha256=report['plan_sha256']),f)
    with tempfile.TemporaryDirectory(prefix='oj-contract-baseline-') as temp:
        baseline=Path(temp)
        for n,sha in plan['baseline_hashes'].items():
            raw=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'show',plan['baseline_commit']+':'+n],cwd=ROOT)
            if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError('Baseline differs from plan')
            p=baseline/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        for arm,source in (('baseline',baseline),('candidate',ROOT)):
            result=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--worker','--mode',mode,'--arm',arm,'--source',str(source),'--output',str(output/arm)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            (output/f'{arm}_process.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
            if result.returncode:
                p=output/arm/'budget.json';ledger=json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
                attempts=len(list((output/arm).glob('request_*.json')))
                report['arms'][arm]=dict(worker_exit_code=result.returncode,partial_budget=ledger,recorded_attempts=attempts)
                report['real_api_attempts']+=attempts
                if ledger is not None: report['known_effective_tokens']+=ledger['known_effective_tokens']
                report['status']='STOPPED_WORKER_ERROR';break
            current=json.loads((output/arm/'report.json').read_text(encoding='utf-8'));report['arms'][arm]=current
            report['real_api_attempts']+=current['actual_http_calls'];report['known_effective_tokens']+=current['effective_tokens']
            write(output/'report.json',report);print(result.stdout,flush=True)
            if current['has_unaccounted_request'] or current['remote_stopped'] or current.get('recording_errors'):
                report['status']='STOPPED_ACCOUNTING_OR_RECORDING';break
    if report['status']=='RUNNING': report['status']='COMPLETED'
    report['frozen_files_unchanged']=all(digest(ROOT/n)==sha for n,sha in plan['frozen_hashes'].items())
    if mode=='offline' and report['status']=='COMPLETED':
        report['offline_passed']=report['real_api_attempts']==0 and all(a['metrics']['verified']==6 and a['metrics']['integrity_passed'] and not a['summary']['budget_state']['events'] for a in report['arms'].values())
    write(output/'report.json',report)
    print(json.dumps({k:report[k] for k in ('status','real_api_attempts','known_effective_tokens')}));print('Report:',output/'report.json')
    return 0 if report['status']=='COMPLETED' and report.get('offline_passed',True) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group();m.add_argument('--live',action='store_true');m.add_argument('--replay',action='store_true')
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);p.add_argument('--mode',choices=['live','offline','replay'],help=argparse.SUPPRESS)
    p.add_argument('--arm',choices=['baseline','candidate'],help=argparse.SUPPRESS);p.add_argument('--source',type=Path,help=argparse.SUPPRESS);p.add_argument('--output',type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.worker: asyncio.run(worker(args))
    else: raise SystemExit(run(args))
