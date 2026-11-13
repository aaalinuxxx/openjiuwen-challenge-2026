"""Independent final submission regression audit; no HTTP."""
import hashlib,json,tempfile
from decimal import Decimal,InvalidOperation
from pathlib import Path
from main_offline_benchmark import verify_coding
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E128_submission_acceptance'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
planpath=BASE/'plan_mixed.json';plan=read(planpath);marker=read(BASE/'plan_mixed_started.json');directory=ROOT/'experiments'/marker['directory'];r=read(directory/'report.json')
assert r['mode']=='LIVE' and r['status']=='COMPLETED' and r['audit']['passed']
assert r['plan_sha256']==marker['plan_sha256']==digest(planpath)
assert r['frozen_files_unchanged'] and all(digest(ROOT/n)==h for n,h in plan['frozen_hashes'].items())
qfiles=sorted(directory.glob('request_*.json'));sfiles=sorted(directory.glob('response_*.json'));events=[e for e in r['budget']['events'] if e['status']!='NOT_SENT']
assert len(qfiles)==len(sfiles)==len(events)==r['actual_http_calls']<=plan['max_calls']
cost=Decimal(0)
for qp,sp,e in zip(qfiles,sfiles,events):
    q=read(qp);s=read(sp);raw=s['response'];u=raw['usage'];amount=Decimal(u['prompt_tokens'])/10+u['completion_tokens'];cost+=amount
    assert q['task_id']==s['task_id']==e['task_id'] and e['status']=='ACCOUNTED' and not e.get('reserve_exceeded')
    assert raw['model']==q['payload']['model'] and raw['model'].endswith('noreason')
    assert q['payload']['max_tokens']==e['output_cap'] and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
    assert not u.get('completion_tokens_details',{}).get('reasoning_tokens',0)
    assert e['input_tokens']==u['prompt_tokens'] and e['output_tokens']==u['completion_tokens'] and Decimal(str(e['effective_cost']))==amount
assert cost==Decimal(str(r['audit']['effective_tokens']))<=plan['budget']
assert not r['budget']['has_unaccounted_request'] and not r['budget']['remote_stopped'] and r['budget']['reserved_effective_tokens']==0
labels=read(ROOT/plan['labels']);assert set(labels)=={x['task_id'] for x in r['rows']}
for row in r['rows']:
    id=row['task_id'];truth=labels[id];source=ROOT/plan['tasks']/id;target=directory/'task_artifacts'/id
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
    assert bool(not truth['unsolvable'] and match and row['status']=='SOLVED' and row['integrity_passed'])==row['verified_solution']
old=read(ROOT/plan['historical_report']);oldids={x['task_id'] for x in old['rows'] if x['verified_solution']};newids={x['task_id'] for x in r['rows'] if x['verified_solution']}
pre=read(BASE/'preflight.json');m=r['metrics']
checks=dict(known26_correct=m['correct']==26,known78_points=m['score']==78,no_lost_tasks=not(oldids-newids),no_wrong_solved=m['incorrect_solved_answers']==0,no_truncations=m['truncations']==0,no_failed_answer_files=m['non_solved_answer_files']==0,integrity=m['integrity_passed'],accounting=True,isolated_cli=pre['passed'],default_calibrated=r['configuration']['ranking_policy']=='calibrated',profile_csv_roomy=r['configuration']['profile']=='csv-roomy')
prior=read(ROOT/'experiments/E127_numeric_recheck_summary.json')
result=dict(accepted=all(checks.values()),checks=checks,metrics=m,new_accounted_calls=len(qfiles),new_effective_tokens=float(cost),report=(directory/'report.json').relative_to(ROOT).as_posix(),report_sha256=digest(directory/'report.json'),runtime_sha256=pre['runtime_sha256'],configuration=r['configuration'],unit_tests=235,campaign_accounted_calls=prior['campaign_accounted_calls']+len(qfiles),campaign_known_effective_tokens=float(Decimal(str(prior['campaign_known_effective_tokens']))+cost),prior_unaccounted_reservation=248.7,docker_tested=False,linux_tested=False,limitations=['Known31-task regression, not hidden-test estimate','Source/CLI tests on Windows; colleague owns Docker/Linux packaging','Experimental numeric correction remains disabled'])
(ROOT/'experiments/E129_submission_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
