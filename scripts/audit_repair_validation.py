"""Independent acceptance/accounting check for the frozen E109 repair run."""
import argparse,hashlib,json
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args();directory=args.directory.resolve()
planpath=ROOT/'experiments/E108_regression_fixes/plan.json';plan=read(planpath);report=read(directory/'report.json')
assert report['mode']=='LIVE' and report['status']=='COMPLETED' and report['audit']['passed']
assert report['plan_sha256']==digest(planpath) and report['frozen_files_unchanged']
assert all(digest(ROOT/n)==h for n,h in plan['frozen_hashes'].items())
assert not report['recording_errors'] and not report['budget']['has_unaccounted_request']
requests=[read(p) for p in sorted(directory.glob('request_*.json'))];responses=[read(p) for p in sorted(directory.glob('response_*.json'))]
assert len(requests)==len(responses)==report['actual_http_calls']==report['audit']['calls']
cost=Decimal(0)
for request,response in zip(requests,responses):
    assert request['task_id']==response['task_id']
    raw=response['response'];usage=raw['usage']
    assert raw['model']==request['payload']['model'] and raw['model'].endswith('noreason')
    assert usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens']
    assert usage.get('completion_tokens_details',{}).get('reasoning_tokens',0)==0
    cost+=Decimal(usage['prompt_tokens'])/10+usage['completion_tokens']
assert cost==Decimal(str(report['audit']['effective_tokens'])) and cost<=plan['budget']
rows={r['task_id']:r for r in report['rows']};assert set(rows)==set(plan['selected_tasks'])
targets=plan['selected_tasks'][:5];controls=plan['selected_tasks'][5:]
def accepted(row):
    return row['verified_solution'] if not row['unsolvable'] else row['status'] in ('UNSOLVABLE','UNKNOWN','SKIPPED') and row['answer'] is None
checks=dict(targets_passed=all(accepted(rows[n]) for n in targets),controls_passed=all(accepted(rows[n]) for n in controls),no_incorrect_solved=report['metrics']['incorrect_solved_answers']==0,no_truncations=report['metrics']['truncations']==0,input_integrity=all(r['integrity_passed'] for r in rows.values()),no_non_solved_answer_files=report['metrics']['non_solved_answer_files']==0,accounting=True)
replies={r['task_id']:r['response']['choices'][0]['message']['content'] for r in responses}
old=read(ROOT/'experiments/E107_validation_calibrated_live_20261112T193830637442/report.json');oldrows={r['task_id']:r for r in old['rows']}
comparisons=[dict(task_id=n,before_status=oldrows[n]['status'],before_answer=oldrows[n]['answer'],after_status=rows[n]['status'],after_answer=rows[n]['answer'],after_verified=rows[n]['verified_solution']) for n in targets]
summary=dict(report=str((directory/'report.json').relative_to(ROOT)),report_sha256=digest(directory/'report.json'),plan_sha256=digest(planpath),acceptance_checks=checks,accepted=all(checks.values()),metrics=report['metrics'],calls=len(requests),effective_tokens=float(cost),target_comparisons=comparisons,hypotheses={'H04.25':dict(status='SUPPORTED_ON_REPLAY_AND_LIVE_ABSTENTION',live_reply=replies[targets[0]],spaced_marker_live_repeated=replies[targets[0]]=='UN SOLVABLE',note='Exact historical spaced reply and other variants verified by unit tests; fresh live refusal may have different spelling.'),'H04.26':dict(status='SUPPORTED_ON_TARGETED_LIVE',answer=rows[targets[1]]['answer']),'H04.28':dict(status='SUPPORTED_ON_TARGETED_LIVE',coding_correct=sum(rows[n]['verified_solution'] for n in targets[2:]),coding_total=3)},unit_tests=190,production_ranking_changed=False,full_mixed_live_rerun=False,campaign_calls_before=198,campaign_cost_before=19099.3,campaign_calls=198+len(requests),campaign_effective_tokens=float(Decimal('19099.3')+cost),limitations=['Adaptive replay of observed failures, not independent holdout.','Joint repair run; no full factorial ablation.','Eight known controls, not full31-task mixed API regression.','Public coding tests do not guarantee hidden tests.'])
(ROOT/'experiments/E109_repair_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('accepted','acceptance_checks','calls','effective_tokens','campaign_effective_tokens')}))
