"""Independent review of the numeric-recheck diagnostic; no new API calls."""
import hashlib,json,tempfile
from decimal import Decimal
from pathlib import Path
from numeric_recheck_policy import CALCULATION_PROMPT,numeric_literal_only,clean_code
from harness.sandbox.executor import run_python_snippet
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E126_numeric_recheck'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
planpath=BASE/'plan.json';plan=read(planpath);marker=read(BASE/'plan_started.json');directory=ROOT/'experiments'/marker['directory'];r=read(directory/'report.json')
assert marker['plan_sha256']==digest(planpath)==r['plan_sha256'] and r['status']=='COMPLETED'
assert all(digest(ROOT/n)==h for n,h in plan['frozen_hashes'].items())
cases={c['case_id']:c for c in read(ROOT/plan['cases'])};labels=read(ROOT/plan['labels'])
reqs=sorted(directory.glob('request_*.json'));resps=sorted(directory.glob('response_*.json'));events=[e for e in r['budget']['events'] if e['status']!='NOT_SENT'];assert len(reqs)==len(resps)==len(events)==10
cost=Decimal(0);correct=0;seen=set();lost=[];wrong=[];history=Decimal(0)
for case in cases.values():
    assert numeric_literal_only(case['initial_code'])
    for key in ('request','response','report'):assert digest(ROOT/case['source_'+key])==case[key+'_sha256']
    history+=Decimal(case['initial_usage']['prompt_tokens'])/10+case['initial_usage']['completion_tokens']
for qpath,spath,event in zip(reqs,resps,events):
    q=read(qpath);s=read(spath);id=q['task_id'];assert id not in seen;seen.add(id)
    assert id==s['task_id']==event['task_id'];case=cases[id];raw=s['response'];u=raw['usage']
    assert q['payload']['messages'][0]['content']==CALCULATION_PROMPT and q['payload']['messages'][1]['content']==case['instruction']
    assert q['payload']['max_tokens']==event['output_cap']==200 and raw['model']==q['payload']['model']=='qwen3.8-27b-noreason'
    assert event['status']=='ACCOUNTED' and not u.get('completion_tokens_details',{}).get('reasoning_tokens',0)
    amount=Decimal(u['prompt_tokens'])/10+u['completion_tokens'];cost+=amount
    assert amount==Decimal(str(event['effective_cost'])) and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
    row=next(x for x in r['rows'] if x['case_id']==id);file=directory/'task_artifacts'/id/'answer.txt'
    answer=file.read_text(encoding='utf-8').strip() if file.exists() else None;assert answer==row['answer']
    assert read(directory/'task_artifacts'/id/'task.json')==dict(task_id=id,task_type='math',instruction=case['instruction'],reward=1)
    code=raw['choices'][0]['message']['content']
    if row['result']['status']=='SOLVED':
        assert raw['choices'][0]['finish_reason']=='stop' and not numeric_literal_only(code)
        with tempfile.TemporaryDirectory() as tmp:
            ok,stdout,err=run_python_snippet(clean_code(code),Path(tmp))
        assert ok and stdout.strip().splitlines()[-1].strip()==answer
        match=Decimal(answer)==Decimal(labels[id]['expected'])
    else:match=False
    assert match==row['verified_solution'];correct+=match
    if labels[id]['baseline_correct'] and not match:lost.append(id)
    if row['result']['status']=='SOLVED' and not match:wrong.append(id)
assert cost==Decimal(str(r['audit']['new_effective_tokens']))<=plan['budget']
assert not r['budget']['has_unaccounted_request'] and r['budget']['reserved_effective_tokens']==0
assert len(r['workflow_runs'])==10 and all(x['state']=='COMPLETED' and x['stages']==['solve','finalize'] for x in r['workflow_runs'])
result=dict(hypothesis='H04.36',report=(directory/'report.json').relative_to(ROOT).as_posix(),report_sha256=digest(directory/'report.json'),accepted_diagnostic=correct>=6 and not lost and not wrong,baseline_correct=4,correct=correct,total_cases=10,unique_instructions=8,lost_controls=lost,wrong_solved=wrong,new_accounted_calls=10,new_effective_tokens=float(cost),historical_initial_cost=float(history),illustrative_combined_cost=float(history+cost),campaign_accounted_calls=499,campaign_known_effective_tokens=float(Decimal('35982.2')+cost),prior_unaccounted_reservation=248.7,production_changed=False,limitations=['Adaptive enriched historical-case diagnostic, not end-to-end contest-score gain','Initial generation cost reused, not charged a second time','AST computation shape does not prove correctness','Prior unknown ledgers retained'])
(ROOT/'experiments/E127_numeric_recheck_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
