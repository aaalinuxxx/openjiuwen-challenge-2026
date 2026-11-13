"""Independent release acceptance and ledger audit; never sends API requests."""
import argparse,hashlib,json
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args();directory=args.directory.resolve()
planpath=ROOT/'experiments/E116_production_ranking/plan.json';plan=read(planpath);r=read(directory/'report.json')
assert r['mode']=='LIVE' and r['status']=='COMPLETED' and r['audit']['passed']
assert r['plan_sha256']==digest(planpath) and r['frozen_files_unchanged'] and not r['recording_errors']
assert all(digest(ROOT/n)==h for n,h in plan['frozen_hashes'].items())
assert r['configuration']['ranking_policy']=='calibrated'
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
assert cost==Decimal(str(r['audit']['effective_tokens'])) and cost<=plan['budget']
assert not r['budget']['has_unaccounted_request'] and r['budget']['reserved_effective_tokens']==0
old=read(ROOT/plan['historical_report']);oldids={x['task_id'] for x in old['rows'] if x['verified_solution']};newids={x['task_id'] for x in r['rows'] if x['verified_solution']}
for row in r['rows']:
    file=directory/'task_artifacts'/row['task_id']/'answer.txt'
    answer=file.read_text(encoding='utf-8').strip() if file.exists() else None
    assert answer==row['answer']
checks=dict(full_26_correct=r['metrics']['correct']==26,full_78_score=r['metrics']['score']==78,all_previous_solutions_retained=not(oldids-newids),no_wrong_solved=r['metrics']['incorrect_solved_answers']==0,no_truncations=r['metrics']['truncations']==0,no_non_solved_answer_files=r['metrics']['non_solved_answer_files']==0,integrity=r['metrics']['integrity_passed'],accounting=True,default_calibrated=True)
out=dict(report=(directory/'report.json').relative_to(ROOT).as_posix(),report_sha256=digest(directory/'report.json'),accepted=all(checks.values()),acceptance_checks=checks,metrics=r['metrics'],calls=len(req),effective_tokens=float(cost),configuration=r['configuration'],lost=sorted(oldids-newids),gained=sorted(newids-oldids),unit_tests=212,campaign_calls=271+len(req),campaign_effective_tokens=float(Decimal('21349.7')+cost),production_ranking='calibrated',production_output_floor=False,rollback='--ranking-policy roi',limitations=['Known31-task regression, not independent hidden-contest performance.','E115 tight-budget ordering advantage does not imply a higher score than78 on this saturated set.','Docker/Linux/read-only packaging remains a separate check.'])
(ROOT/'experiments/E117_release_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ('accepted','metrics','calls','effective_tokens','campaign_effective_tokens')}))
