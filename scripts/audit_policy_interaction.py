"""Audit sequential four-arm evidence; charge only new calls to campaign."""
import argparse,json,hashlib
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E114_policy_interaction'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(directory,planpath):
    directory=directory.resolve();r=read(directory/'report.json');p=read(planpath)
    assert r['mode']=='LIVE' and r['status']=='COMPLETED' and r['audit']['passed']
    assert r['plan_sha256']==digest(planpath) and r['frozen_files_unchanged'] and not r['recording_errors']
    assert all(digest(ROOT/n)==h for n,h in p['frozen_hashes'].items())
    req=[read(x) for x in sorted(directory.glob('request_*.json'))];resp=[read(x) for x in sorted(directory.glob('response_*.json'))]
    paid=[e for e in r['budget']['events'] if e['status']!='NOT_SENT'];assert len(req)==len(resp)==len(paid)==r['actual_http_calls']
    cost=Decimal(0)
    for q,s,e in zip(req,resp,paid):
        raw=s['response'];u=raw['usage'];amount=Decimal(u['prompt_tokens'])/10+u['completion_tokens']
        assert q['task_id']==s['task_id']==e['task_id'] and e['status']=='ACCOUNTED'
        assert q['payload']['model']==raw['model'] and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
        assert u.get('completion_tokens_details',{}).get('reasoning_tokens',0)==0
        assert Decimal(str(e['effective_cost']))==amount and e['output_cap']==q['payload']['max_tokens']
        cost+=amount
    assert cost==Decimal(str(r['audit']['effective_tokens'])) and cost<=p['budget']==500
    assert not r['budget']['has_unaccounted_request'] and r['budget']['reserved_effective_tokens']==0
    val=dict(report=(directory/'report.json').relative_to(ROOT).as_posix(),report_sha256=digest(directory/'report.json'),metrics=r['metrics'],calls=len(req),effective_tokens=float(cost),floor_denials=sum(e['status']=='NOT_SENT' and e.get('error_type')=='OUTPUT_CAP_BELOW_FLOOR' for e in r['budget']['events']))
    return r,p,read(directory/'ranking.json'),val
p=argparse.ArgumentParser();p.add_argument('--calibrated-baseline',required=True,type=Path);p.add_argument('--calibrated-floor',required=True,type=Path);args=p.parse_args()
reuse=read(BASE/'reused_evidence.json');reports={};plans={};ranks={};values={}
for arm,evidence in reuse['reused_arms'].items():
    reportpath=ROOT/evidence['report'];assert digest(reportpath)==evidence['sha256']
    reports[arm],plans[arm],ranks[arm],values[arm]=load(reportpath.parent,ROOT/evidence['plan'])
for arm,directory in [('calibrated_baseline',args.calibrated_baseline),('calibrated_floor',args.calibrated_floor)]:
    reports[arm],plans[arm],ranks[arm],values[arm]=load(directory,BASE/(arm+'_plan.json'))
base=plans['roi_baseline'];reference=reports['roi_baseline'];rowmap={r['task_id']:r for r in ranks['roi_baseline']}
for arm,p in plans.items():
    assert all(p['frozen_hashes'][n]==h for n,h in base['frozen_hashes'].items())
    assert (p['tasks'],p['labels'],p['profile'],p['concurrency'],p['max_calls'])==(base['tasks'],base['labels'],base['profile'],base['concurrency'],base['max_calls'])
    assert reports[arm]['configuration']==reference['configuration']
    assert len(ranks[arm])==len(rowmap)
    assert all(r['reward']==rowmap[r['task_id']]['reward'] and r['expected_cost']==rowmap[r['task_id']]['expected_cost'] for r in ranks[arm])
assert ranks['roi_baseline']==ranks['roi_floor'] and ranks['calibrated_baseline']==ranks['calibrated_floor']
combo=values['calibrated_floor'];others=[v for k,v in values.items() if k!='calibrated_floor']
key=lambda v:(v['metrics']['score'],-v['effective_tokens'])
checks=dict(combination_best_score_cost=all(key(combo)>=key(v) for v in others),higher_score_than_original=combo['metrics']['score']>values['roi_baseline']['metrics']['score'],wrong_solved_not_increased=all(combo['metrics']['incorrect_solved_answers']<=v['metrics']['incorrect_solved_answers'] for v in others),integrity=all(v['metrics']['integrity_passed'] for v in values.values()),accounting=True)
score=lambda arm:values[arm]['metrics']['score']
roi_effect=score('roi_floor')-score('roi_baseline');cal_effect=score('calibrated_floor')-score('calibrated_baseline')
newarms=['calibrated_baseline','calibrated_floor'];calls=sum(values[a]['calls'] for a in newarms);cost=round(sum(values[a]['effective_tokens'] for a in newarms),1)
bs={r['task_id'] for r in reference['rows'] if r['verified_solution']};cs={r['task_id'] for r in reports['calibrated_floor']['rows'] if r['verified_solution']}
out=dict(hypothesis='H04.30',combination_accepted=all(checks.values()),acceptance_checks=checks,arms=values,best_observed_arm=max(values,key=lambda a:key(values[a])),floor_score_effect_under_roi=roi_effect,floor_score_effect_under_calibrated=cal_effect,descriptive_score_interaction=cal_effect-roi_effect,new_calls=calls,new_effective_tokens=cost,four_arm_calls=sum(v['calls'] for v in values.values()),four_arm_effective_tokens=round(sum(v['effective_tokens'] for v in values.values()),1),campaign_calls=239+calls,campaign_effective_tokens=round(20623.8+cost,1),combination_gained_vs_original=sorted(cs-bs),combination_lost_vs_original=sorted(bs-cs),production_changed=False,overall_internal_ceiling_removed_by_user=True,limitations=['Sequential fixed-order four-arm comparison with two reused recent live arms.','Identical frozen code/data does not remove model or time variation.','One known100-task seed and tight budget500, not independent holdout.','Interaction is descriptive without statistical confidence or universal claim.','Production integration/full mixed regression not yet performed.'])
(ROOT/'experiments/E115_interaction_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ('combination_accepted','acceptance_checks','best_observed_arm','floor_score_effect_under_roi','floor_score_effect_under_calibrated','descriptive_score_interaction','new_calls','new_effective_tokens','campaign_effective_tokens')}))
