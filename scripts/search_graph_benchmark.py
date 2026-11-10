"""Synthetic search development suite; no API, no claims about hidden tests."""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import TaskContext
from harness.agents.search_solver import solve_search_task

class NeedsAPI(Exception): pass
class Offline:
    async def complete(self,**kwargs): raise NeedsAPI()

async def run(label,seed):
    rng=random.Random(seed)
    rows=[]
    dataset=[]
    with tempfile.TemporaryDirectory(prefix='oj-search-') as tmp:
        for i in range(12):
            # New entities, distractors and values; expected values computed here,
            # independently of the query interpreter under test.
            surname=('Arbor','Birch','Cedar','Dahl','Elm','Frost','Green','Hale',
                     'Ivory','Jones','Klein','Lake')[i]
            a,b,c=f'Ada {surname}',f'Bela {surname}',f'Cora {surname}'
            firm=f'Orbit Company{i}'
            city=rng.choice(['Riga','Turku','Lima','Bern'])+str(i)
            born=str(rng.randint(1950,2000))
            mentor_born=str(rng.randint(1940,1990))
            founded=str(rng.randint(1980,2020))
            docs={'a.md':f'# {a}\nBorn: {born}\nMentor: {b}\nEmployer: {firm}\n',
                  'b.md':f'# {b}\nBorn: {mentor_born}\nMentor: {c}\nEmployer: {firm}\n',
                  'c.md':f'# {c}\nEmployer: {firm}\n',
                  'firm.md':f'# {firm}\nHeadquarters: {city}\nFounded: {founded}\n',
                  'noise.md':'# Other Company\nHeadquarters: Distractor\n'}
            cases=[
                ('born',f'In which year was {a} born?',born,'SOLVED',{}),
                ('hq2',f"In which city is the headquarters of {a}'s employer?",city,'SOLVED',{}),
                ('hq3',f"In which city is the headquarters of {a}'s mentor's employer?",city,'SOLVED',{}),
                ('hq4',f"In which city is the headquarters of {a}'s mentor's mentor's employer?",city,'SOLVED',{}),
                ('mentor_born',f"In which year was {a}'s mentor born?",mentor_born,'SOLVED',{}),
                ('founded',f'In which year was {firm} founded?',founded,'SOLVED',{}),
                ('missing_entity','In which year was Missing Person born?',None,'UNSOLVABLE',{}),
                ('broken_link',f"In which city is the headquarters of {a}'s mentor's employer?",None,'UNSOLVABLE',{'b.md':f'# {b}\nEmployer: Missing Company\n'}),
                ('missing_field',f"In which city is the headquarters of {a}'s employer?",None,'UNSOLVABLE',{'firm.md':f'# {firm}\nFounded: {founded}\n'}),
                ('historical_qualifier',f"In which city is the headquarters of {a}'s employer in 1999?",None,'UNKNOWN',{}),
                ('duplicate_title',f'In which year was {a} born?',None,'UNKNOWN',{'duplicate.md':f'# {a}\nBorn: {int(born)+1}\n'})]
            for family,question,expected,wanted,overrides in cases:
                files={**docs,**overrides}
                name=f'{family}_{i}'
                work=Path(tmp)/name
                kb=work/'kb'
                kb.mkdir(parents=True)
                for filename,content in files.items():
                    (kb/filename).write_text(content,encoding='utf-8')
                instruction='The directory kb/ contains markdown records. '+question+' Write ONLY the answer to answer.txt.'
                ctx=TaskContext(name,'search',instruction,1,work,work,0,False)
                try:
                    result=await solve_search_task(ctx,Offline())
                    status,answer=result.status,result.answer
                except NeedsAPI:
                    status,answer='NEEDS_API',None
                correct=(status=='SOLVED' and answer==expected) if wanted=='SOLVED' else (
                    status=='UNSOLVABLE' if wanted=='UNSOLVABLE' else status in ('UNKNOWN','NEEDS_API'))
                rows.append(dict(task_id=name,family=family,expected_status=wanted,
                    status=status,answer=answer,expected_answer=expected,correct=correct,
                    wrong_answer=status=='SOLVED' and (wanted!='SOLVED' or answer!=expected)))
                dataset.append(dict(id=name,instruction=instruction,files=files,expected=expected,status=wanted))
    summary=dict(total=len(rows),correct=sum(r['correct'] for r in rows),
        solvable=sum(r['expected_status']=='SOLVED' for r in rows),
        solved_correct=sum(r['correct'] and r['expected_status']=='SOLVED' for r in rows),
        wrong_answers=sum(r['wrong_answer'] for r in rows),
        needs_api=sum(r['status']=='NEEDS_API' for r in rows),
        correctly_rejected=sum(r['correct'] and r['expected_status']=='UNSOLVABLE' for r in rows),
        api_calls=0)
    report=dict(label=label,seed=seed,scope='synthetic development suite; no API comparison',
        solver_sha256=hashlib.sha256((ROOT/'harness/agents/search_solver.py').read_bytes()).hexdigest(),
        dataset_sha256=hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest(),
        summary=summary,rows=rows)
    output=ROOT/'experiments'/f'{label}.json'
    with output.open('x',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--label',required=True)
    p.add_argument('--seed',type=int,default=914)
    a=p.parse_args()
    if not a.label.replace('_','').replace('-','').isalnum(): p.error('Invalid label')
    asyncio.run(run(a.label,a.seed))
