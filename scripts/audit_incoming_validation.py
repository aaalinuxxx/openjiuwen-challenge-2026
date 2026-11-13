"""Independent accounting and predeclared acceptance for H04.27."""
import argparse,json,hashlib
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E110_incoming_context'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(directory,arm):
    directory=directory.resolve();r=read(directory/'report.json');planpath=BASE/(arm+'_plan.json');p=read(planpath)
    assert r['mode']=='LIVE' and r['status']=='COMPLETED' and r['audit']['passed']
    assert r['plan_sha256']==digest(planpath) and r['frozen_files_unchanged']
    assert not r['recording_errors'] and all(digest(ROOT/n)==h for n,h in p['frozen_hashes'].items())
    reqs=[read(x) for x in sorted(directory.glob('request_*.json'))];responses=[read(x) for x in sorted(directory.glob('response_*.json'))]
    assert len(reqs)==len(responses)==r['actual_http_calls']
    cost=Decimal(0)
    for q,s in zip(reqs,responses):
        raw=s['response'];u=raw['usage']
        assert q['task_id']==s['task_id'] and raw['model']==q['payload']['model']
        assert u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
        assert u.get('completion_tokens_details',{}).get('reasoning_tokens',0)==0
        cost+=Decimal(u['prompt_tokens'])/10+u['completion_tokens']
    assert cost==Decimal(str(r['audit']['effective_tokens'])) and cost<=p['budget']
    return r,p,{q['task_id']:q['payload'] for q in reqs},dict(report=str((directory/'report.json').relative_to(ROOT)),report_sha256=digest(directory/'report.json'),metrics=r['metrics'],calls=len(reqs),effective_tokens=float(cost))
p=argparse.ArgumentParser();p.add_argument('--forward',type=Path,required=True);p.add_argument('--incoming',type=Path,required=True);args=p.parse_args()
f,pf,qf,vf=load(args.forward,'forward');i,pi,qi,vi=load(args.incoming,'incoming')
assert pf['frozen_hashes']==pi['frozen_hashes'] and pf['budget']==pi['budget']==600
assert f['configuration']==i['configuration'] and qf.keys()==qi.keys()
for n in qf:
    for field in ('model','max_tokens','temperature'):assert qf[n][field]==qi[n][field]
rf={r['task_id']:r for r in f['rows']};ri={r['task_id']:r for r in i['rows']};assert rf.keys()==ri.keys()
labels=read(BASE/'labels.json');inverse=['validate_086_fresh_search_inverse','incoming_employer','incoming_then_outgoing']
controls=[n for n,t in labels.items() if t['group']=='E110_control']
assert all(qf[n]==qi[n] for n in controls if n in qf)
def abstains(r):return r['answer'] is None and r['status'] in ('UNKNOWN','UNSOLVABLE','SKIPPED')
checks=dict(all_six_solvable=i['metrics']['correct']==6,two_correct_abstentions=all(abstains(r) for r in i['rows'] if r['unsolvable']),no_wrong_solved=i['metrics']['incorrect_solved_answers']==0,no_truncations=i['metrics']['truncations']==0,integrity=i['metrics']['integrity_passed'],all_baseline_solutions_retained=all(ri[n]['verified_solution'] for n in rf if rf[n]['verified_solution']),inverse_gain=sum(ri[n]['verified_solution'] for n in inverse)>sum(rf[n]['verified_solution'] for n in inverse),accounting=True)
rows=[dict(task_id=n,group=labels[n]['group'],forward_status=rf[n]['status'],forward_answer=rf[n]['answer'],forward_correct=rf[n]['verified_solution'],incoming_status=ri[n]['status'],incoming_answer=ri[n]['answer'],incoming_correct=ri[n]['verified_solution']) for n in rf]
cost=round(vf['effective_tokens']+vi['effective_tokens'],1);calls=vf['calls']+vi['calls']
out=dict(hypothesis='H04.27',accepted=all(checks.values()),acceptance_checks=checks,arms={'forward':vf,'incoming':vi},comparison=rows,inverse_correct={'forward':sum(rf[n]['verified_solution'] for n in inverse),'incoming':sum(ri[n]['verified_solution'] for n in inverse)},calls=calls,effective_tokens=cost,campaign_calls=210+calls,campaign_effective_tokens=round(19659.8+cost,1),unit_tests=199,production_ranking_changed=False,full_mixed_live_rerun=False,limitations=['Three inverse targets: one observed failure and two new small authored cases.','One fixed-order live pair, not a statistical or external holdout guarantee.','Bounded priority retrieval is not complete search of all graph paths.','Full mixed/coding regression was not rerun over API.'])
(ROOT/'experiments/E111_incoming_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ('accepted','acceptance_checks','inverse_correct','calls','effective_tokens','campaign_effective_tokens')}))
