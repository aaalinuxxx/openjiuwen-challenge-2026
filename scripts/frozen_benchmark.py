"""Frozen single-run SDK experiments. Offline by default; real API requires --live."""
import argparse, asyncio, json, shutil, tempfile, time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api_settings import load_settings
from main_offline_benchmark import hashes, verify_coding
from multimodule_live import write, digest
from run_agent import parse_args, build_config
from harness.planner.scheduler import TaskScheduler
from harness.agents.base_harness import OpenJiuwenLLMBridge


def metrics(rows):
    return dict(total=len(rows),solvable=sum(not r['unsolvable'] for r in rows),
        correct=sum(r['verified_solution'] for r in rows),
        score=sum(r['reward'] for r in rows if r['verified_solution']),
        max_score=sum(r['reward'] for r in rows if not r['unsolvable']),
        incorrect_solved_answers=sum(r['incorrect_solved_answer'] for r in rows),
        non_solved_answer_files=sum(r['answer'] is not None and r['status']!='SOLVED' for r in rows),
        justified_refusals=sum(r['justified_refusal'] for r in rows),
        truncations=sum(r['status']=='TRUNCATED' for r in rows),
        integrity_passed=all(r['integrity_passed'] for r in rows))


def audit(directory,summary,plan,live):
    events=[e for e in summary['budget_state']['events'] if e['status']!='NOT_SENT']
    requests=sorted(directory.glob('request_*.json'));responses=sorted(directory.glob('response_*.json'))
    checks=[];cost=Decimal(0);details=[]
    checks.append(len(requests)==len(responses)==len(events))
    for req,res,event in zip(requests,responses,events):
        request=json.loads(req.read_text());record=json.loads(res.read_text());payload=request['payload'];raw=record['response'];usage=raw['usage']
        # Frozen experiments only allow noreason models; nonzero reasoning is a failed audit.
        inp=usage['prompt_tokens'];out=usage['completion_tokens'];reason=usage.get('completion_tokens_details',{}).get('reasoning_tokens',0)
        amount=Decimal(inp)/10+out;cost+=amount
        passed=(request['task_id']==record['task_id']==event['task_id'] and event['status']=='ACCOUNTED'
            and payload['model'].endswith('noreason') and raw.get('model')==payload['model'] and reason==0
            and event['input_tokens']==inp and event['output_tokens']==out and event['reasoning_tokens']==0
            and usage['total_tokens']==inp+out and Decimal(str(event['effective_cost']))==amount
            and payload['max_tokens']==event['output_cap'])
        checks.append(passed);details.append(dict(task_id=request['task_id'],cost=float(amount),model=payload['model'],cap=payload['max_tokens'],finish=raw['choices'][0]['finish_reason'],passed=passed))
    checks.extend([abs(float(cost)-summary['effective_tokens_spent'])<1e-7,
        not summary['budget_state']['has_unaccounted_request'],not summary['budget_state']['remote_stopped'],
        summary['budget_state']['reserved_effective_tokens']==0,
        float(cost)<=plan['budget'] if live else cost==0,len(requests)<=plan['max_calls'] if live else not requests])
    result=dict(passed=all(checks),calls=len(requests),effective_tokens=float(cost),requests=details)
    write(directory/'independent_audit.json',result);return result


async def run(args):
    planpath=args.plan.resolve();plan=json.loads(planpath.read_text(encoding='utf-8'))
    for name,sha in plan['frozen_hashes'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen input changed: '+name)
    source=ROOT/plan['tasks'];labels=json.loads((ROOT/plan['labels']).read_text(encoding='utf-8'))
    if plan.get('selected_tasks'):labels={n:labels[n] for n in plan['selected_tasks']}
    if not labels:raise ValueError('Empty fixture')
    settings=load_settings() if args.live else dict(LLM_BASE_URL='https://fixture.invalid/v1',LLM_API_KEY='offline')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=ROOT/'experiments'/(plan['output_prefix']+('_live_' if args.live else '_offline_')+stamp)
    if args.live:
        with (planpath.parent/(planpath.stem+'_started.json')).open('x',encoding='utf-8') as f:
            json.dump(dict(directory=directory.name,plan_sha256=digest(planpath)),f)
    directory.mkdir(parents=True);started=time.monotonic()
    report=dict(status='RUNNING',mode='LIVE' if args.live else 'OFFLINE_ZERO_BUDGET',hypothesis=plan['hypothesis'],plan_sha256=digest(planpath),recording_errors=[])
    write(directory/'report.json',report);print('Report:',directory/'report.json',flush=True)
    with tempfile.TemporaryDirectory(prefix='oj-evening-') as temp:
        taskroot=Path(temp)/'tasks';taskroot.mkdir()
        for name,t in labels.items():
            shutil.copytree(source/name,taskroot/name)
            public=json.loads((taskroot/name/'task.json').read_text(encoding='utf-8'))
            if set(public)!={'task_id','task_type','instruction','reward'} or public['task_id']!=name:
                raise ValueError('Unexpected public metadata')
            if any((taskroot/name).rglob('answer.txt')):raise ValueError('Answer leakage')
        initial={n:hashes(taskroot/n) for n in labels}
        protected={n:{p.relative_to(taskroot/n):p.read_bytes() for p in (taskroot/n).rglob('test_*.py')} for n in labels}
        argv=['--tasks-dir',str(taskroot),'--profile',plan.get('profile','validated'),'--budget',str(plan['budget'] if args.live else 0),
            '--max-api-calls',str(plan['max_calls'] if args.live else 0)]
        config=build_config(parse_args(argv),settings=settings,audit_path=directory/'budget.json')
        config.max_concurrency=plan.get('concurrency',1)
        requests=0;original=OpenJiuwenLLMBridge._get_transport
        class RecordingScheduler(TaskScheduler):
            async def _run_single(self,item):
                result=await super()._run_single(item)
                write(directory/'progress.json',dict(results=self.results,budget=self.budget_tracker.snapshot()))
                print(json.dumps(dict(task_id=result.task_id,status=result.status,cost=result.effective_cost)),flush=True)
                return result
        scheduler=RecordingScheduler(config)
        write(directory/'ranking.json',[{k:r[k] for k in ('task_id','roi','expected_cost','reward')} for r in scheduler.discover_and_rank_tasks()])
        report['configuration']=dict(profile=plan.get('profile','validated'),multi_csv_max_output_tokens=config.multi_csv_max_output_tokens,budget=config.initial_budget_tokens,max_calls=config.max_api_calls,
            concurrency=config.max_concurrency,experimental_joins=config.experimental_joins,
            search_min_task_budget=config.search_min_task_budget,data_min_task_budget=config.data_min_task_budget,coding_min_task_budget=config.coding_min_task_budget)
        def recording_transport(bridge):
            if not args.live:raise AssertionError('Offline HTTP forbidden')
            if report['recording_errors']:raise RuntimeError('Previous response recording failed')
            transport=original(bridge)
            async def send(payload):
                nonlocal requests
                idx=requests+1
                write(directory/f'request_{idx:02d}.json',dict(task_id=bridge.task_id,payload=payload))
                requests=idx
                response=await transport(payload)
                try:write(directory/f'response_{idx:02d}.json',dict(task_id=bridge.task_id,response=response))
                except OSError:report['recording_errors'].append(idx)
                return response
            return send
        try:
            with patch.object(OpenJiuwenLLMBridge,'_get_transport',recording_transport):summary=await scheduler.run_all()
            report['summary']=summary;rows=[]
            for n,t in labels.items():
                root=taskroot/n;f=root/'answer.txt';answer=f.read_text(encoding='utf-8').strip() if f.is_file() else None
                result=summary['task_results'].get(n,{});status=result.get('status','SKIPPED' if n in summary['skipped_tasks'] else 'NOT_RUN')
                final=hashes(root);changed=[p for p,h in initial[n].items() if final.get(p)!=h]
                unexpected=[p for p in final if p not in initial[n] and p!='answer.txt']
                allowed=set(t.get('allowed_changes',['mylib.py'])) if t['task_type']=='coding' else set()
                integrity=not unexpected and not(set(changed)-allowed)
                match=answer is not None and answer==str(t['expected'])
                if t.get('comparison')=='decimal' or t['group']=='E75_pilot':
                    try:match=answer is not None and Decimal(answer).is_finite() and Decimal(answer)==Decimal(t['expected'])
                    except InvalidOperation:match=False
                if t['task_type']=='coding':match=not t['unsolvable'] and verify_coding(root,protected[n],answer)
                correct=bool(not t['unsolvable'] and match and status=='SOLVED' and integrity)
                rows.append(dict(task_id=n,task_type=t['task_type'],group=t['group'],reward=t['reward'],unsolvable=t['unsolvable'],
                    expected=t['expected'],answer=answer,status=status,verified_solution=correct,incorrect_solved_answer=status=='SOLVED' and not match,
                    justified_refusal=t['unsolvable'] and answer is None and status in ('UNSOLVABLE','SKIPPED'),
                    integrity_passed=integrity,changed_files=changed,unexpected_files=unexpected,result=result))
            report.update(rows=rows,metrics=metrics(rows),by_type={t:metrics([r for r in rows if r['task_type']==t]) for t in sorted(set(r['task_type'] for r in rows))})
            report['audit']=audit(directory,summary,plan,args.live)
            report['status']='COMPLETED' if report['audit']['passed'] and not report['recording_errors'] else 'STOPPED_ACCOUNTING_OR_RECORDING'
            if not args.live:
                report['offline_passed']=requests==0 and not summary['budget_state']['events'] and report['metrics']['integrity_passed']
                if plan.get('offline_correct') is not None:report['offline_passed'] &= report['metrics']['correct']==plan['offline_correct']
            if plan.get('historical_report'):
                old=json.loads((ROOT/plan['historical_report']).read_text(encoding='utf-8'))
                if plan.get('historical_arm'):old=old['arms'][plan['historical_arm']]
                oldids={r['task_id'] for r in old['rows'] if r['verified_solution']};newids={r['task_id'] for r in rows if r['verified_solution']}
                report['historical_comparison']=dict(note='Historical comparison, not simultaneous causal A/B',lost=sorted(oldids-newids),gained=sorted(newids-oldids))
        except Exception as e:
            report.update(status='WORKER_ERROR',error_type=type(e).__name__)
            raise
        finally:
            report.update(actual_http_calls=requests,elapsed_seconds=round(time.monotonic()-started,3),
                budget=scheduler.budget_tracker.snapshot(),frozen_files_unchanged=all(digest(ROOT/n)==sha for n,sha in plan['frozen_hashes'].items()))
            shutil.copytree(taskroot,directory/'task_artifacts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            write(directory/'report.json',report)
    print(json.dumps({k:report.get(k) for k in ('status','metrics','audit','historical_comparison','offline_passed')}),flush=True)
    return 0 if report['status']=='COMPLETED' and report.get('offline_passed',True) and report['frozen_files_unchanged'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--live',action='store_true')
    raise SystemExit(asyncio.run(run(p.parse_args())))
