"""Independent H04.33 audit; reuse baselines without recharging their cost."""
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import audit_two_pass as shared
ROOT=shared.ROOT
BASE=ROOT/'experiments/E120_math_budget'
def main():
    old=shared.read(ROOT/'experiments/E119_two_pass_summary.json')
    reuse=shared.read(BASE/'reused_baselines.json');arms={};pairs={}
    for budget in (800,2000):
        reference=reuse[str(budget)];assert shared.digest(ROOT/reference['report'])==reference['sha256']
        baseline=shared.audit_arm('baseline_'+str(budget))
        with patch.object(shared,'BASE',BASE):candidate=shared.audit_arm(str(budget))
        directory=ROOT/'experiments'/candidate['directory'];report=shared.read(directory/'report.json')
        labels=shared.read(ROOT/'experiments/E118_two_pass/labels.json')
        spent=0;math_caps=[]
        for e in report['budget']['events']:
            if e['status']=='NOT_SENT':continue
            if labels[e['task_id']]['task_type']=='math':
                expected=min(200,(budget*10-spent-e['input_token_estimate'])//10)
                assert e['output_cap']==expected
                math_caps.append(dict(task_id=e['task_id'],cap=e['output_cap']))
            spent+=int(Decimal(str(e['effective_cost']))*10)
        candidate['math_caps']=math_caps
        arms[str(budget)]=candidate
        pairs[str(budget)]=dict(baseline_score=baseline['metrics']['score'],candidate_score=candidate['metrics']['score'],score_delta=candidate['metrics']['score']-baseline['metrics']['score'],cost_delta=round(candidate['effective_tokens']-baseline['effective_tokens'],6),lost=sorted(set(baseline['correct_ids'])-set(candidate['correct_ids'])),gained=sorted(set(candidate['correct_ids'])-set(baseline['correct_ids'])))
    safe=all(a['metrics']['incorrect_solved_answers']==0 and a['metrics']['integrity_passed'] and a['metrics']['non_solved_answer_files']==0 for a in arms.values())
    accepted=safe and all(p['score_delta']>=0 for p in pairs.values()) and any(p['score_delta']>0 for p in pairs.values())
    cost=round(sum(a['effective_tokens'] for a in arms.values()),6);calls=sum(a['calls'] for a in arms.values())
    result=dict(hypothesis='H04.33',acceptance_passed=accepted,arms=arms,paired=pairs,reused_baselines=reuse,new_calls=calls,new_effective_tokens=cost,campaign_calls=old['campaign_calls']+calls,campaign_effective_tokens=round(old['campaign_effective_tokens']+cost,6),production_changed=False,limitations=['Adaptive follow-up on same24 authored tasks','Historical baseline reuse with unchanged source hashes, not independent holdout','No broad superiority or statistical significance claim'])
    (ROOT/'experiments/E121_math_budget_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
