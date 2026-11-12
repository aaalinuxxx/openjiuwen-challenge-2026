"""Compare frozen E107 live arms; no model calls or fitted thresholds."""
import argparse, hashlib, json
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def metrics(rows):
    return dict(total=len(rows),solvable=sum(not r['unsolvable'] for r in rows),correct=sum(r['verified_solution'] for r in rows),score=sum(r['reward'] for r in rows if r['verified_solution']),max_score=sum(r['reward'] for r in rows if not r['unsolvable']),incorrect_solved=sum(r['incorrect_solved_answer'] for r in rows),truncations=sum(r['status']=='TRUNCATED' for r in rows),integrity_passed=all(r['integrity_passed'] for r in rows))
def load(directory,arm):
    directory=directory.resolve()
    report=read(directory/'report.json');plan=read(ROOT/'experiments/E106_ranking_validation_plans'/f'{arm}_plan.json')
    assert report['mode']=='LIVE' and report['status']=='COMPLETED' and report['audit']['passed']
    assert report['frozen_files_unchanged'] and not report['recording_errors']
    assert report['plan_sha256']==digest(ROOT/'experiments/E106_ranking_validation_plans'/f'{arm}_plan.json')
    assert all(digest(ROOT/p)==h for p,h in plan['frozen_hashes'].items())
    requests=[read(p) for p in sorted(directory.glob('request_*.json'))]
    responses=[read(p) for p in sorted(directory.glob('response_*.json'))]
    assert len(requests)==len(responses)==report['actual_http_calls']==report['audit']['calls']
    cost=Decimal(0)
    for req,res in zip(requests,responses):
        assert req['task_id']==res['task_id']
        usage=res['response']['usage'];cost+=Decimal(usage['prompt_tokens'])/10+usage['completion_tokens']
    assert cost==Decimal(str(report['audit']['effective_tokens'])) and cost<=plan['budget']
    fresh={r['task_id'] for r in report['rows'] if r['group']=='E105_fresh'}
    fresh_attempted=sorted({r['task_id'] for r in requests}&fresh)
    value=dict(report=str(directory.relative_to(ROOT)/'report.json'),report_sha256=digest(directory/'report.json'),overall=metrics(report['rows']),fresh=metrics([r for r in report['rows'] if r['task_id'] in fresh]),seen=metrics([r for r in report['rows'] if r['task_id'] not in fresh]),calls=len(requests),effective_tokens=float(cost),fresh_api_attempted=fresh_attempted,fresh_api_attempted_count=len(fresh_attempted),fresh_results=[dict(task_id=r['task_id'],status=r['status'],correct=r['verified_solution'],reward=r['reward'],api_attempted=r['task_id'] in fresh_attempted) for r in report['rows'] if r['task_id'] in fresh])
    return report,plan,read(directory/'ranking.json'),value
p=argparse.ArgumentParser();p.add_argument('--calibrated',required=True,type=Path);p.add_argument('--roi',required=True,type=Path);args=p.parse_args()
c,pc,rc,vc=load(args.calibrated,'calibrated');r,pr,rr,vr=load(args.roi,'roi')
assert pc['frozen_hashes']==pr['frozen_hashes']
assert pc['budget']==pr['budget']==1000
assert c['configuration']==r['configuration']
rcm={x['task_id']:x for x in rc};rrm={x['task_id']:x for x in rr}
assert rcm.keys()==rrm.keys()
assert all(rcm[n]['expected_cost']==rrm[n]['expected_cost'] and rcm[n]['reward']==rrm[n]['reward'] for n in rcm)
assert [x['task_id'] for x in rc]!=[x['task_id'] for x in rr]
checks=dict(higher_total_score=vc['overall']['score']>vr['overall']['score'],fresh_score_not_lower=vc['fresh']['score']>=vr['fresh']['score'],wrong_solved_not_increased=vc['overall']['incorrect_solved']<=vr['overall']['incorrect_solved'],integrity_passed=vc['overall']['integrity_passed'] and vr['overall']['integrity_passed'],fresh_api_coverage_at_least_6=vc['fresh_api_attempted_count']>=6,accounting_passed=True)
cs={x['task_id'] for x in c['rows'] if x['verified_solution']};rs={x['task_id'] for x in r['rows'] if x['verified_solution']}
out=dict(hypothesis='H04.24',arms=dict(calibrated=vc,roi=vr),acceptance_checks=checks,accepted_on_this_fixture=all(checks.values()),gained=sorted(cs-rs),lost=sorted(rs-cs),new_calls=vc['calls']+vr['calls'],new_effective_tokens=round(vc['effective_tokens']+vr['effective_tokens'],1),prior_evening_calls=153,prior_evening_effective_tokens=17354.3,production_ranking_changed=False,limitations=['Author-generated validation; not external contest holdout.','76 familiar copies plus24 new tasks; fresh subgroup reported separately.','One seed and one live run per arm; no statistical universal-superiority claim.','Budget denied tasks do not validate solver quality.'])
out['evening_calls']=153+out['new_calls'];out['evening_effective_tokens']=round(17354.3+out['new_effective_tokens'],1)
(ROOT/'experiments/E107_validation_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ('acceptance_checks','accepted_on_this_fixture','new_calls','new_effective_tokens','evening_effective_tokens')}))
