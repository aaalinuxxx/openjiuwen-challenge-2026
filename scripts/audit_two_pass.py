"""Recompute H04.32 accounting, policy decisions and paired pilot results."""
import json, hashlib
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from main_offline_benchmark import verify_coding
BASE=ROOT/'experiments/E118_two_pass'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def audit_arm(name):
    path=BASE/('plan_'+name+'.json'); plan=read(path)
    marker=read(path.with_name(path.stem+'_started.json'))
    assert marker['plan_sha256']==digest(path)
    directory=ROOT/'experiments'/marker['directory'];report=read(directory/'report.json')
    assert report['status']=='COMPLETED' and report['mode']=='LIVE'
    assert report['plan_sha256']==digest(path) and report['frozen_files_unchanged']
    assert all(digest(ROOT/n)==h for n,h in plan['frozen_hashes'].items())
    assert report['configuration']['budget']==plan['budget']
    assert report['configuration']['ranking_policy']=='calibrated'
    budget=report['budget'];events=[e for e in budget['events'] if e['status']!='NOT_SENT']
    reqs=sorted(directory.glob('request_*.json'));resps=sorted(directory.glob('response_*.json'))
    assert len(events)==len(reqs)==len(resps)==report['actual_http_calls']<=plan['max_calls']
    total=Decimal(0);per_task={};truncated=0
    for request,response,event in zip(reqs,resps,events):
        q=read(request);r=read(response);raw=r['response'];usage=raw['usage']
        assert q['task_id']==r['task_id']==event['task_id']
        assert event['status']=='ACCOUNTED' and not event.get('reserve_exceeded')
        assert raw['model']==q['payload']['model'] and raw['model'].endswith('noreason')
        assert q['payload']['max_tokens']==event['output_cap']
        assert usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens']
        assert not usage.get('completion_tokens_details',{}).get('reasoning_tokens',0)
        cost=Decimal(usage['prompt_tokens'])/10+usage['completion_tokens']
        assert cost==Decimal(str(event['effective_cost']))
        assert event['input_tokens']==usage['prompt_tokens'] and event['output_tokens']==usage['completion_tokens']
        total+=cost;per_task[q['task_id']]=per_task.get(q['task_id'],Decimal(0))+cost
        truncated+=raw['choices'][0]['finish_reason']=='length'
    assert total<=plan['budget'] and abs(float(total)-budget['known_effective_tokens'])<1e-7
    assert not budget['has_unaccounted_request'] and not budget['remote_stopped'] and budget['reserved_effective_tokens']==0
    labels=read(ROOT/plan['labels']);assert {r['task_id'] for r in report['rows']}==set(labels)
    for row in report['rows']:
        result=row['result']; cost=Decimal(result.get('input_tokens',0))/10+result.get('output_tokens',0)+result.get('reasoning_tokens',0)
        assert cost==per_task.get(row['task_id'],Decimal(0))
        answer=directory/'task_artifacts'/row['task_id']/'answer.txt'
        assert (answer.read_text(encoding='utf-8').strip() if answer.exists() else None)==row['answer']
        source=ROOT/plan['tasks']/row['task_id']; copy=directory/'task_artifacts'/row['task_id']
        allowed={'mylib.py'} if row['task_type']=='coding' else set()
        for f in source.rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc':
                rel=f.relative_to(source)
                if rel.as_posix() not in allowed:assert digest(f)==digest(copy/rel)
        truth=labels[row['task_id']]
        assert row['expected']==truth['expected'] and row['reward']==truth['reward']
        match=row['answer'] is not None and row['answer']==str(truth['expected'])
        if truth.get('comparison')=='decimal':
            try:match=row['answer'] is not None and Decimal(row['answer']).is_finite() and Decimal(row['answer'])==Decimal(truth['expected'])
            except InvalidOperation:match=False
        if truth['task_type']=='coding':
            protected={f.relative_to(source):f.read_bytes() for f in source.rglob('test_*.py')}
            match=not truth['unsolvable'] and verify_coding(copy,protected,row['answer'])
        actual=bool(not truth['unsolvable'] and match and row['status']=='SOLVED' and row['integrity_passed'])
        assert actual==row['verified_solution']
        assert (row['status']=='SOLVED' and not match)==row['incorrect_solved_answer']
        original_names={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        final_names={p.relative_to(copy).as_posix() for p in copy.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        assert not final_names-original_names-{'answer.txt'}
    metrics=report['metrics']
    assert metrics['score']==sum(r['reward'] for r in report['rows'] if r['verified_solution'])
    assert metrics['correct']==sum(r['verified_solution'] for r in report['rows'])
    retry=[]; first_score=None;first_cost=None
    if plan['arm']=='two_pass':
        policy=report['summary']['two_pass'];attempts=policy['attempts']
        repeated=[a for a in attempts if a['pass_number']==2]
        assert max(Counter(a['task_id'] for a in repeated).values(),default=0)<=1
        decisions={d['task_id']:d for d in policy['decisions']}
        first={a['task_id']:a for a in attempts if a['pass_number']==1}
        for a in repeated:
            assert first[a['task_id']]['result']['status'] in ('TRUNCATED','FAILED')
            assert decisions[a['task_id']]['retried']
            assert decisions[a['task_id']]['remaining']>=decisions[a['task_id']]['required_reserve']
            assert all(r['first_cap']==r['requested_cap'] for r in a['requests'])
            retry.append(dict(task_id=a['task_id'],before=first[a['task_id']]['result']['status'],after=a['result']['status'],cost=a['effective_cost_delta'],actual_output_caps=[e['output_cap'] for e in events if e['task_id']==a['task_id']]))
        assert abs(sum(a['effective_cost_delta'] for a in attempts)-float(total))<1e-7
        first_cost=round(sum(a['effective_cost_delta'] for a in first.values()),6)
        first_score=sum(r['reward'] for r in report['rows'] if r['verified_solution'] and first.get(r['task_id'],{}).get('result',{}).get('status')=='SOLVED')
    return dict(directory=directory.name,report_sha256=digest(directory/'report.json'),metrics=metrics,calls=len(events),effective_tokens=float(total),raw_truncations=truncated,retries=retry,first_pass_score=first_score,first_pass_cost=first_cost,correct_ids=[r['task_id'] for r in report['rows'] if r['verified_solution']],incorrect=[dict(task_id=r['task_id'],expected=r['expected'],answer=r['answer']) for r in report['rows'] if r['incorrect_solved_answer']],audit_passed=True)

def main():
    arms={n:audit_arm(n) for n in ('baseline_800','two_pass_800','two_pass_2000','baseline_2000')}
    pairs={}
    for budget in (800,2000):
        a=arms['baseline_'+str(budget)];b=arms['two_pass_'+str(budget)]
        pairs[str(budget)]=dict(score_delta=b['metrics']['score']-a['metrics']['score'],cost_delta=round(b['effective_tokens']-a['effective_tokens'],6),gained=sorted(set(b['correct_ids'])-set(a['correct_ids'])),lost=sorted(set(a['correct_ids'])-set(b['correct_ids'])))
    safe=all(a['metrics']['incorrect_solved_answers']==0 and a['metrics']['integrity_passed'] and a['metrics']['non_solved_answer_files']==0 for a in arms.values())
    acceptance=safe and all(p['score_delta']>=0 for p in pairs.values()) and any(p['score_delta']>0 for p in pairs.values())
    cost=round(sum(a['effective_tokens'] for a in arms.values()),6);calls=sum(a['calls'] for a in arms.values())
    result=dict(hypothesis='H04.32',acceptance_passed=acceptance,arms=arms,paired=pairs,new_calls=calls,new_effective_tokens=cost,campaign_calls=294+calls,campaign_effective_tokens=round(23138.8+cost,6),production_changed=False,limitations=['Small sequential pilot, no significance claim','New authored instances of familiar families, not organizer hidden holdout','Fixed caps are one candidate, not all possible two-pass strategies'])
    (ROOT/'experiments/E119_two_pass_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
