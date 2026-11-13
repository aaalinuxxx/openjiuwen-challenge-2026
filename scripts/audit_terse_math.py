"""H04.35 staged audit using the same frozen evaluator and raw-usage checks."""
import argparse,json
from unittest.mock import patch
import audit_compact_math as parent
from terse_math_benchmark import TERSE_MATH_PROMPT
shared=parent.shared;ROOT=shared.ROOT;BASE=ROOT/'experiments/E124_terse_math'
def check(name):
    with patch.object(parent,'BASE',BASE),patch.object(parent,'COMPACT_MATH_PROMPT',TERSE_MATH_PROMPT):return parent.check(name)
def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['target','fresh'],required=True);args=p.parse_args()
    refs=shared.read(BASE/'reused_baselines.json');target={};pairs={}
    for budget in (800,2000):
        ref=refs[str(budget)];assert shared.digest(ROOT/ref['path'])==ref['sha256']
        baseline=shared.audit_arm('baseline_'+str(budget));candidate=check('target_'+str(budget))
        target[str(budget)]=candidate;pairs[str(budget)]=parent.pair(baseline,candidate)
    accepted=parent.safe(target.values()) and all(r['score_delta']>=0 for r in pairs.values()) and any(r['score_delta']>0 for r in pairs.values())
    result=dict(hypothesis='H04.35',stage=args.stage,target_acceptance=accepted,target=target,target_pairs=pairs,production_changed=False)
    billed=list(target.values())
    if args.stage=='fresh':
        baseline=check('fresh_baseline_replacement');candidate=check('fresh_compact');comparison=parent.pair(baseline,candidate)
        result.update(fresh_baseline=baseline,fresh_compact=candidate,fresh_pair=comparison)
        result['fresh_acceptance']=parent.safe([baseline,candidate]) and comparison['score_delta']>=0 and not comparison['lost']
        result['ready_for_integration_regression']=accepted and result['fresh_acceptance'];billed.extend([baseline,candidate])
    previous=shared.read(ROOT/'experiments/E123_compact_target_summary.json')
    calls=sum(a['calls'] for a in billed);cost=round(sum(a['effective_tokens'] for a in billed),6)
    review=shared.read(BASE/'connection_failure_review.json')
    failed=ROOT/'experiments'/review['failed_directory']
    assert shared.digest(failed/'report.json')==review['failed_report_sha256']
    failure=shared.read(failed/'report.json')
    assert failure['budget']['has_unaccounted_request'] and failure['budget']['reserved_effective_tokens']==248.7
    result.update(interrupted_trial=review,unaccounted_attempts=1,outstanding_reserved_effective_tokens=248.7,transport_attempts=calls+1)
    result.update(new_calls=calls,new_effective_tokens=cost,campaign_calls=previous['campaign_calls']+calls,campaign_effective_tokens=round(previous['campaign_effective_tokens']+cost,6),limitations=['Adaptive development, failed H04.34 retained','Fresh math tasks frozen before variant outcomes','Sequential small trials, no significance claim','No hidden-organizer-set performance claim'])
    (ROOT/'experiments'/('E125_terse_'+args.stage+'_summary.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
