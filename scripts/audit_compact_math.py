"""Independent staged audit of compact math prompt trials."""
import argparse,json
from pathlib import Path
from unittest.mock import patch
import audit_two_pass as shared
from compact_math_benchmark import COMPACT_MATH_PROMPT
ROOT=shared.ROOT;BASE=ROOT/'experiments/E122_compact_math'
def check(name):
    with patch.object(shared,'BASE',BASE):result=shared.audit_arm(name)
    plan=shared.read(BASE/('plan_'+name+'.json'));labels=shared.read(ROOT/plan['labels'])
    directory=ROOT/'experiments'/result['directory'];math=[]
    for file in sorted(directory.glob('request_*.json')):
        request=shared.read(file);task=labels[request['task_id']];payload=request['payload']
        if task['task_type']=='math':
            assert payload['messages'][1]['content']==task['instruction']
            assert payload['model']=='qwen3.8-27b-noreason' and payload['max_tokens']<=200
            if plan['arm']=='compact':assert payload['messages'][0]['content']==COMPACT_MATH_PROMPT
            else:assert payload['messages'][0]['content']!=COMPACT_MATH_PROMPT
            response=shared.read(file.with_name(file.name.replace('request_','response_')))['response']
            text=response['choices'][0]['message']['content']
            math.append(dict(task_id=task['task_id'],actual_cap=payload['max_tokens'],output_tokens=response['usage']['completion_tokens'],finish=response['choices'][0]['finish_reason'],comment_lines=sum(line.lstrip().startswith('#') for line in text.splitlines()),has_markdown='\x60\x60\x60' in text))
    result['math_generations']=math;return result

def pair(a,b):
    return dict(baseline_score=a['metrics']['score'],candidate_score=b['metrics']['score'],score_delta=b['metrics']['score']-a['metrics']['score'],cost_delta=round(b['effective_tokens']-a['effective_tokens'],6),lost=sorted(set(a['correct_ids'])-set(b['correct_ids'])),gained=sorted(set(b['correct_ids'])-set(a['correct_ids'])))
def safe(arms):return all(a['metrics']['incorrect_solved_answers']==0 and a['metrics']['integrity_passed'] and a['metrics']['non_solved_answer_files']==0 for a in arms)
def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['target','fresh'],required=True);args=p.parse_args()
    refs=shared.read(BASE/'reused_baselines.json');target={};pairs={}
    for budget in (800,2000):
        ref=refs[str(budget)];assert shared.digest(ROOT/ref['path'])==ref['sha256']
        baseline=shared.audit_arm('baseline_'+str(budget));candidate=check('target_'+str(budget))
        target[str(budget)]=candidate;pairs[str(budget)]=pair(baseline,candidate)
    accepted=safe(target.values()) and all(r['score_delta']>=0 for r in pairs.values()) and any(r['score_delta']>0 for r in pairs.values())
    result=dict(hypothesis='H04.34',stage=args.stage,target_acceptance=accepted,target=target,target_pairs=pairs,production_changed=False)
    billed=list(target.values())
    if args.stage=='fresh':
        baseline=check('fresh_baseline');candidate=check('fresh_compact');comparison=pair(baseline,candidate)
        result.update(fresh_baseline=baseline,fresh_compact=candidate,fresh_pair=comparison)
        result['fresh_acceptance']=safe([baseline,candidate]) and comparison['score_delta']>=0 and not comparison['lost']
        result['ready_for_integration_regression']=accepted and result['fresh_acceptance']
        billed.extend([baseline,candidate])
    calls=sum(a['calls'] for a in billed);cost=round(sum(a['effective_tokens'] for a in billed),6)
    result.update(new_calls=calls,new_effective_tokens=cost,campaign_calls=396+calls,campaign_effective_tokens=round(30362.1+cost,6),limitations=['Sequential small authored-task experiment','Targeted replay is adaptive; fresh tasks frozen before candidate outputs','Actual cap may change with input reservation length','No claims about organizer hidden tests'])
    (ROOT/'experiments'/('E123_compact_'+args.stage+'_summary.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
