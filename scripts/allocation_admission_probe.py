"""Offline admission checks against recorded prompts; zero HTTP requests."""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.planner.budget_tracker import BudgetTracker,BudgetDenied
from multimodule_live import write,digest
FIXTURE=ROOT/'experiments/E79_budget_allocation'
PREVIOUS=ROOT/'experiments/E78_mixed_live_20261111T201608442567/candidate'

async def main():
 labels=json.loads((ROOT/'experiments/E77_mixed_integration/labels.json').read_text(encoding='utf-8'))
 ranking={r['task_id']:r for r in json.loads((PREVIOUS/'ranking.json').read_text(encoding='utf-8'))}
 inputs=[]
 for p in sorted(PREVIOUS.glob('request_*.json')):
  q=json.loads(p.read_text(encoding='utf-8'));task=q['task_id'];kind=labels[task]['task_type']
  if kind not in ('search','data_analysis'):continue
  desired=32 if kind=='search' else (400 if task=='data_two_file_join' else 200)
  inputs.append((task,kind,q['payload'],desired,p))
 p=ROOT/'experiments/E76_join_or_live_20261111T200417736373/request_06.json'
 inputs.append(('pilot_extra_numeric_control','data_analysis',json.loads(p.read_text(encoding='utf-8'))['payload'],400,p))
 rows=[]
 for task,kind,payload,desired,source in inputs:
  estimate=len(''.join(m['content'] for m in payload['messages']).encode('utf-8'))+1024
  for profile,minimum in [('baseline',0),('candidate',300 if kind=='search' else 700)]:
   tracker=BudgetTracker(3000)
   task_budget=tracker.allocate_task_budget(ranking[task]['expected_cost'],ranking[task]['reward'],minimum)
   try:
    ticket,cap=await tracker.reserve(task,task_budget,estimate,desired)
    await tracker.not_sent(ticket,'OFFLINE_PROBE_NO_HTTP')
    status='ADMITTED'
   except BudgetDenied:cap=0;status='DENIED'
   if profile=='candidate':assert cap==desired,(task,cap,desired)
   assert tracker.spent_effective_tokens==0 and not tracker.has_unaccounted_request
   rows.append(dict(task=task,profile=profile,task_budget=task_budget,input_reserve=estimate/10,
                    requested_output_cap=desired,admitted_output_cap=cap,status=status,
                    source=source.relative_to(ROOT).as_posix(),source_sha256=digest(source)))
 limits=[]
 for total in (0,100,250):
  tracker=BudgetTracker(total)
  budget=tracker.allocate_task_budget(85,3,700)
  assert budget<=total
  try:
   ticket,cap=await tracker.reserve('limited',budget,2130,400)
   assert cap==37 and total==250
   await tracker.not_sent(ticket,'OFFLINE_PROBE_NO_HTTP')
  except BudgetDenied:cap=0;assert total<213
  limits.append(dict(global_remaining=total,allocated=budget,output_cap=cap))
 write(FIXTURE/'admission_validation.json',dict(api_calls=0,passed=True,rows=rows,remaining_budget_controls=limits,
       scope='Synthetic admission against recorded prompt byte lengths; not a live quality result'))
 print(json.dumps(dict(api_calls=0,passed=True,prompt_cases=len(inputs),profile_rows=len(rows))))
if __name__=='__main__':asyncio.run(main())
