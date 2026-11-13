"""Independent matched-budget admission-floor audit; no API calls."""
import argparse,json,hashlib
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E112_output_floor'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(directory,arm):
    directory=directory.resolve();r=read(directory/'report.json');pp=BASE/(arm+'_plan.json');p=read(pp)
    assert r['mode']=='LIVE' and r['status']=='COMPLETED' and r['audit']['passed']
    assert r['plan_sha256']==digest(pp) and r['frozen_files_unchanged'] and not r['recording_errors']
    assert all(digest(ROOT/n)==h for n,h in p['frozen_hashes'].items())
    req=[read(x) for x in sorted(directory.glob('request_*.json'))];resp=[read(x) for x in sorted(directory.glob('response_*.json'))]
    events=r['budget']['events'];paid=[e for e in events if e['status']!='NOT_SENT']
    assert len(req)==len(resp)==len(paid)==r['actual_http_calls']
    cost=Decimal(0)
    for q,s,e in zip(req,resp,paid):
        raw=s['response'];u=raw['usage'];amount=Decimal(u['prompt_tokens'])/10+u['completion_tokens']
        assert q['task_id']==s['task_id']==e['task_id'] and e['status']=='ACCOUNTED'
        assert raw['model']==q['payload']['model'] and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
        assert u.get('completion_tokens_details',{}).get('reasoning_tokens',0)==0
        assert Decimal(str(e['effective_cost']))==amount and e['output_cap']==q['payload']['max_tokens']
        cost+=amount
    assert cost==Decimal(str(r['audit']['effective_tokens'])) and cost<=p['budget']
    assert not r['budget']['has_unaccounted_request'] and r['budget']['reserved_effective_tokens']==0
    denials=[e for e in events if e['status']=='NOT_SENT' and e.get('error_type')=='OUTPUT_CAP_BELOW_FLOOR']
    labels=read(ROOT/p['labels'])
    for e in denials:
        assert e['output_cap']<p['output_floors'][labels[e['task_id']]['task_type']]
        assert 'effective_cost' not in e
    val=dict(report=str((directory/'report.json').relative_to(ROOT)),report_sha256=digest(directory/'report.json'),metrics=r['metrics'],calls=len(req),effective_tokens=float(cost),floor_denials=[dict(task_id=e['task_id'],output_cap=e['output_cap'],floor=p['output_floors'][labels[e['task_id']]['task_type']],prior_paid_calls=sum(x['task_id']==e['task_id'] and x['ticket']<e['ticket'] for x in paid)) for e in denials])
    return r,p,read(directory/'ranking.json'),val
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--floor',type=Path,required=True);args=p.parse_args()
b,pb,rb,vb=load(args.baseline,'baseline');f,pf,rf,vf=load(args.floor,'floor')
assert pb['frozen_hashes']==pf['frozen_hashes'] and pb['budget']==pf['budget']==500
assert rb==rf and b['configuration']==f['configuration']
br={r['task_id']:r for r in b['rows']};fr={r['task_id']:r for r in f['rows']};assert br.keys()==fr.keys()
checks=dict(floor_exercised=bool(vf['floor_denials']),fewer_truncations=f['metrics']['truncations']<b['metrics']['truncations'],wrong_solved_not_increased=f['metrics']['incorrect_solved_answers']<=b['metrics']['incorrect_solved_answers'],integrity=f['metrics']['integrity_passed'] and b['metrics']['integrity_passed'],score_or_tie_cost_improves=f['metrics']['score']>b['metrics']['score'] or (f['metrics']['score']==b['metrics']['score'] and vf['effective_tokens']<vb['effective_tokens']),accounting=True)
bs={n for n,r in br.items() if r['verified_solution']};fs={n for n,r in fr.items() if r['verified_solution']}
cost=round(vb['effective_tokens']+vf['effective_tokens'],1);calls=vb['calls']+vf['calls']
out=dict(hypothesis='H04.29',accepted=all(checks.values()),acceptance_checks=checks,arms={'baseline':vb,'floor':vf},gained=sorted(fs-bs),lost=sorted(bs-fs),floor_rejected_tasks_comparison=[dict(task_id=n,baseline_status=br[n]['status'],baseline_correct=br[n]['verified_solution'],floor_status=fr[n]['status'],reward=fr[n]['reward']) for n in sorted({e['task_id'] for e in vf['floor_denials']})],calls=calls,effective_tokens=cost,campaign_calls=224+calls,campaign_effective_tokens=round(19899.5+cost,1),unit_tests=206,production_changed=False,limitations=['Adaptive known100-task workload; not fresh holdout.','One fixed-order live pair, no universal threshold calibration.','All omitted tasks count against score; fewer truncations alone is not success.','Floor admission only: larger math caps were not tested.'])
(ROOT/'experiments/E113_floor_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ('accepted','acceptance_checks','calls','effective_tokens','campaign_effective_tokens')}))
