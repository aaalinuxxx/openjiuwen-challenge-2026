"""Paired offline development benchmark for H04, independent arithmetic oracles."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import TaskContext
from harness.agents.data_solver import solve_data_task
from harness.agents.math_solver import solve_math_task
class NeedsAPI(Exception): pass
class Offline:
    async def complete(self,**kwargs): raise NeedsAPI()

async def run(label):
    rng=random.Random(607)
    specs=[]
    for i in range(10):
        n=rng.randint(500,1500)
        d=rng.randint(2,7)
        add=rng.randint(10,50)
        base=f'A warehouse starts with {n} boxes. '
        tail=' How many boxes does it have at the end? Write ONLY the answer to answer.txt.'
        for family,body,expected,status in [
            ('math_known',f'It ships {d} boxes per day for 3 days.',str(n-d*3),'SOLVED'),
            ('math_add',f'It receives {add} boxes.',str(n+add),'SOLVED'),
            ('math_sub',f'It ships {add} boxes.',str(n-add),'SOLVED'),
            ('math_round',f'Then the stock is split equally into {d} warehouses and it keeps one share (rounded down). Then the stock is doubled by merging with a sister warehouse.',str((n//d)*2),'SOLVED'),
            ('math_partial',f'It ships {d} boxes per day for 3 days and then loses 5 boxes.',None,'UNKNOWN'),
            ('math_zero','Then the stock is split equally into 0 warehouses and it keeps one share (rounded down).',None,'UNSOLVABLE')]:
            specs.append(dict(id=f'{family}_{i}',kind='math',instruction=base+body+tail,files={},expected=expected,status=status))
        # Two selected rows, one outside the range, one different product.
        u,v=rng.randint(1,20)*2,rng.randint(1,20)*2
        csv=('order_id,region,product,month,units,price\n'
             f'1,north,widget,2,{u},0.10\n2,south,widget,3,{v},0.20\n'
             '3,north,widget,4,999,8\n4,north,gadget,2,888,9\n')
        cases=[
            ('sum',"How many units of product 'widget' were sold in months 2 through 3 inclusive?",str(u+v),'SOLVED',csv),
            ('region',"How many units of product 'widget' in region 'north' were sold in months 2 through 3 inclusive?",str(u),'SOLVED',csv),
            ('revenue',"What is the total revenue from product 'widget' sold in months 2 through 3 inclusive?",format((u*10+v*20)/100,'.2f').rstrip('0').rstrip('.'),'SOLVED',csv),
            ('count',"How many rows for product 'widget' are in months 2 through 3 inclusive?",'2','SOLVED',csv),
            ('mean',"What is the average units per row for product 'widget' in months 2 through 3 inclusive?",str((u+v)//2),'SOLVED',csv),
            ('max',"What is the maximum units per row for product 'widget' in months 2 through 3 inclusive?",str(max(u,v)),'SOLVED',csv),
            ('empty_sum',"How many units of product 'missing' were sold in months 2 through 3 inclusive?",'0','SOLVED',csv),
            ('empty_mean',"What is the average units per row for product 'missing' in months 2 through 3 inclusive?",None,'UNKNOWN',csv),
            ('missing_column',"How many units of product 'widget' were sold in months 2 through 3 inclusive?",None,'UNSOLVABLE','product,month\nwidget,2\n'),
            ('invalid_number',"How many units of product 'widget' were sold in months 2 through 3 inclusive?",None,'UNKNOWN',csv.replace(f',{u},0.10',',unknown,0.10')),
            ('qualifier',"How many units of product 'widget' were sold in months 2 through 3 inclusive excluding refunded orders?",None,'UNKNOWN',csv)]
        for family,q,expected,status,content in cases:
            specs.append(dict(id=f'csv_{family}_{i}',kind='data_analysis',instruction=q+' Write ONLY the answer to answer.txt.',files={'sales.csv':content},expected=expected,status=status))
    rows=[]
    with tempfile.TemporaryDirectory(prefix='oj-calc-') as tmp:
        for spec in specs:
            work=Path(tmp)/spec['id']; work.mkdir()
            for name,data in spec['files'].items(): (work/name).write_text(data,encoding='utf-8')
            ctx=TaskContext(spec['id'],spec['kind'],spec['instruction'],1,work,work,0,False)
            try:
                result=await (solve_math_task if spec['kind']=='math' else solve_data_task)(ctx,Offline())
                status,answer=result.status,result.answer
            except NeedsAPI: status,answer='NEEDS_API',None
            except Exception as exc: status,answer='ERROR_'+type(exc).__name__,None
            correct=(status=='SOLVED' and answer==spec['expected']) if spec['status']=='SOLVED' else (
                status=='UNSOLVABLE' if spec['status']=='UNSOLVABLE' else status in ('UNKNOWN','NEEDS_API'))
            rows.append(dict(task_id=spec['id'],expected_status=spec['status'],status=status,answer=answer,
                expected_answer=spec['expected'],correct=correct,
                wrong_answer=status=='SOLVED' and (spec['status']!='SOLVED' or answer!=spec['expected'])))
    summary=dict(total=len(rows),solvable=sum(s['status']=='SOLVED' for s in specs),
        solved_correct=sum(r['correct'] and r['expected_status']=='SOLVED' for r in rows),
        wrong_answers=sum(r['wrong_answer'] for r in rows),
        correct_behavior=sum(r['correct'] for r in rows),
        errors=sum(r['status'].startswith('ERROR_') for r in rows),api_calls=0)
    paths=[ROOT/'harness/agents/data_solver.py',ROOT/'harness/agents/math_solver.py',ROOT/'harness/agents/calculation_plans.py']
    report=dict(label=label,scope='synthetic dev; no LLM comparison',summary=summary,rows=rows,
        dataset_sha256=hashlib.sha256(json.dumps(specs,sort_keys=True).encode()).hexdigest(),
        source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()})
    with (ROOT/'experiments'/f'{label}.json').open('x',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--label',required=True); a=p.parse_args()
    if not a.label.replace('_','').isalnum(): p.error('Invalid label')
    asyncio.run(run(a.label))
