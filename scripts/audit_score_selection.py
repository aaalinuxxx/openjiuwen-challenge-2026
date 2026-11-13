"""Re-score saved answers and verify raw HTTP usage; never calls API."""
import hashlib,json
from decimal import Decimal,InvalidOperation
from pathlib import Path
from main_offline_benchmark import verify_coding
from score_selection_benchmark import BASELINE_MATH_PROMPT,TERSE_MATH_PROMPT,CALCULATION_PROMPT,numeric_literal_only
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E130_score_selection'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit_plan(planpath,check_sources=True):
    plan=read(planpath);marker=read(planpath.with_name(planpath.stem+'_started.json'));directory=ROOT/'experiments'/marker['directory'];r=read(directory/'report.json')
    assert r['mode']=='LIVE' and r['status']=='COMPLETED' and r['audit']['passed']
    assert r['plan_sha256']==marker['plan_sha256']==digest(planpath)
    assert r['frozen_files_unchanged']
    if check_sources:assert all(digest(ROOT/n)==h for n,h in plan['frozen_hashes'].items())
    qs=sorted(directory.glob('request_*.json'));ss=sorted(directory.glob('response_*.json'));events=[e for e in r['budget']['events'] if e['status']!='NOT_SENT']
    assert len(qs)==len(ss)==len(events)==r['actual_http_calls']<=plan['max_calls']
    labels=read(ROOT/plan['labels']);cost=Decimal(0);permath={};corrections=0
    for qp,sp,e in zip(qs,ss,events):
        q=read(qp);s=read(sp);raw=s['response'];u=raw['usage'];amount=Decimal(u['prompt_tokens'])/10+u['completion_tokens'];cost+=amount
        assert q['task_id']==s['task_id']==e['task_id'] and e['status']=='ACCOUNTED' and not e.get('reserve_exceeded')
        assert raw['model']==q['payload']['model'] and raw['model'].endswith('noreason')
        assert q['payload']['max_tokens']==e['output_cap'] and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
        assert not u.get('completion_tokens_details',{}).get('reasoning_tokens',0)
        assert e['input_tokens']==u['prompt_tokens'] and e['output_tokens']==u['completion_tokens'] and Decimal(str(e['effective_cost']))==amount
        if labels[q['task_id']]['task_type']=='math':
            previous=permath.setdefault(q['task_id'],[]);prompt=q['payload']['messages'][0]['content']
            arm=plan['arm']
            if not previous:assert prompt==(BASELINE_MATH_PROMPT if arm=='baseline' else TERSE_MATH_PROMPT)
            else:
                assert arm=='terse_recheck' and len(previous)==1 and prompt==CALCULATION_PROMPT
                assert previous[0]['choices'][0]['finish_reason']!='length' and numeric_literal_only(previous[0]['choices'][0]['message']['content'])
                corrections+=1
            assert q['payload']['messages'][1]['content']==labels[q['task_id']]['instruction']
            previous.append(raw)
    assert cost==Decimal(str(r['audit']['effective_tokens']))==Decimal(str(r['budget']['known_effective_tokens']))<=plan['budget']
    assert not r['budget']['has_unaccounted_request'] and not r['budget']['remote_stopped'] and r['budget']['reserved_effective_tokens']==0
    assert set(labels)=={x['task_id'] for x in r['rows']}
    correct=[];score=0;artifact_score=0;artifact_ids=[];status_mismatches=[]
    for row in r['rows']:
        name=row['task_id'];truth=labels[name];source=ROOT/plan['tasks']/name;target=directory/'task_artifacts'/name
        file=target/'answer.txt';answer=file.read_text(encoding='utf-8').strip() if file.exists() else None;assert answer==row['answer']
        match=answer is not None and answer==str(truth['expected'])
        if truth.get('comparison')=='decimal' or truth['group']=='E75_pilot':
            try:match=answer is not None and Decimal(answer).is_finite() and Decimal(answer)==Decimal(truth['expected'])
            except InvalidOperation:match=False
        if truth['task_type']=='coding':
            protected={p.relative_to(source):p.read_bytes() for p in source.rglob('test_*.py')}
            match=not truth['unsolvable'] and verify_coding(target,protected,answer)
        allowed=set(truth.get('allowed_changes',['mylib.py'])) if truth['task_type']=='coding' else set()
        for p in source.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
                rel=p.relative_to(source)
                if rel.as_posix() not in allowed:assert digest(p)==digest(target/rel)
        assert row['integrity_passed'] and not row['unexpected_files']
        verified=bool(not truth['unsolvable'] and match and row['status']=='SOLVED')
        assert verified==row['verified_solution']
        assert (row['status']=='SOLVED' and not match)==row['incorrect_solved_answer']
        if not truth['unsolvable'] and match:
            artifact_score+=truth['reward'];artifact_ids.append(name)
            if row['status']!='SOLVED':status_mismatches.append(name)
        if verified:correct.append(name);score+=truth['reward']
    assert score==r['metrics']['score'] and len(correct)==r['metrics']['correct']
    return dict(arm=plan['arm'],budget=plan['budget'],artifact_score=artifact_score,artifact_correct_ids=artifact_ids,status_mismatches=status_mismatches,score=score,max_score=r['metrics']['max_score'],correct=len(correct),correct_ids=correct,wrong=r['metrics']['incorrect_solved_answers'],truncations=r['metrics']['truncations'],calls=len(qs),effective_tokens=float(cost),correction_calls=corrections,report=(directory/'report.json').relative_to(ROOT).as_posix(),report_sha256=digest(directory/'report.json'))
def audit_interrupted(directory):
    path=ROOT/'experiments'/directory;ledger=read(path/'budget.json')
    events=[e for e in ledger['events'] if e['status']=='ACCOUNTED'];unknown=[e for e in ledger['events'] if e['status']=='COST_UNKNOWN_STOPPED']
    responses=sorted(path.glob('response_*.json'));requests=sorted(path.glob('request_*.json'))
    assert len(responses)==len(events) and len(requests)==len(events)+len(unknown)
    cost=Decimal(0)
    for resp,req,event in zip(responses,requests,events):
        raw=read(resp);q=read(req);u=raw['response']['usage'];amount=Decimal(u['prompt_tokens'])/10+u['completion_tokens'];cost+=amount
        assert raw['task_id']==q['task_id']==event['task_id'] and amount==Decimal(str(event['effective_cost']))
        assert raw['response']['model']==q['payload']['model'] and q['payload']['max_tokens']==event['output_cap']
        assert u['prompt_tokens']==event['input_tokens'] and u['completion_tokens']==event['output_tokens']
        assert u['total_tokens']==u['prompt_tokens']+u['completion_tokens'] and not u.get('completion_tokens_details',{}).get('reasoning_tokens',0)
    assert cost==Decimal(str(ledger['known_effective_tokens'])) and unknown and ledger['has_unaccounted_request']
    return dict(directory=directory,known_calls=len(events),known_effective_tokens=float(cost),unaccounted_requests=len(unknown),reserved_unknown=ledger['reserved_effective_tokens'],report_sha256=digest(path/'report.json'),ledger_sha256=digest(path/'budget.json'),errors=[e['error_type'] for e in unknown],excluded_from_selection=True)
def main():
    design=read(BASE/'design.json');completion=read(BASE/'completion_schedule.json');arms=completion['eligible_arms']
    names=[n for n in design['schedule'] if read(BASE/('plan_'+n+'.json'))['arm'] in arms]
    runs={name:audit_plan(BASE/('plan_'+name+'.json')) for name in names};totals={}
    for arm in arms:
        rs=[r for r in runs.values() if r['arm']==arm];assert len(rs)==3
        totals[arm]=dict(artifact_score=sum(r['artifact_score'] for r in rs),normalized_score=sum(r['score']/r['max_score'] for r in rs),raw_score=sum(r['score'] for r in rs),effective_tokens=round(sum(r['effective_tokens'] for r in rs),6),calls=sum(r['calls'] for r in rs),wrong=sum(r['wrong'] for r in rs))
    order=sorted(totals,key=lambda arm:(-totals[arm]['artifact_score'],totals[arm]['effective_tokens'],arm))
    original=read(BASE/'plan_known_3000_terse_recheck_started.json')['directory']
    replacement=read(BASE/'plan_known_3000_terse_recheck_replacement_started.json')['directory']
    interrupted=[audit_interrupted(original),audit_interrupted(replacement)]
    calls=sum(r['calls'] for r in runs.values())+sum(r['known_calls'] for r in interrupted)
    cost=round(sum(r['effective_tokens'] for r in runs.values())+sum(r['known_effective_tokens'] for r in interrupted),6)
    result=dict(accepted=True,selected_arm=order[0],criterion='Maximize total reward of correct saved answer.txt artifacts across the completed equal-budget comparisons; tie-break actual token cost. Internal SOLVED status is diagnostic only.',metric_amendment=read(BASE/'metric_correction.json'),runs=runs,totals=totals,new_calls=calls,new_effective_tokens=cost,interrupted_trials=interrupted,ineligible_arm='terse_recheck',ineligible_reason=completion['reason'],new_unaccounted_reservation=sum(r['reserved_unknown'] for r in interrupted),prior_unaccounted_reservation=248.7,campaign_accounted_calls=522+calls,campaign_known_effective_tokens=round(38370.4+cost,6),limitations=[design['limitations'],'Third candidate has no completed comparable regression and is not eligible. Transport failures do not establish a policy-quality regression.'])
    (ROOT/'experiments/E131_score_selection_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('selected_arm','totals','new_calls','new_effective_tokens')}))
if __name__=='__main__':main()
