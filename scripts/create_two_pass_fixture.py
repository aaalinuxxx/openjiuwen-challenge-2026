"""Fresh authored fixtures; deterministic references stay outside solver task roots."""
import csv, io, json, math, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'experiments/E118_two_pass'
LABELS={}; CHECKS=[]
def add(name,kind,instruction,expected,reward=3,files=None,unsolvable=False):
    label=dict(task_id=name,task_type=kind,instruction=instruction,reward=reward,
               expected=str(expected),unsolvable=unsolvable,group='E118_fresh')
    if kind in ('math','data_analysis') and not unsolvable:label['comparison']='decimal'
    LABELS[name]=label
    folder=DEST/'tasks'/name;folder.mkdir(parents=True,exist_ok=True)
    (folder/'task.json').write_text(json.dumps({k:label[k] for k in ('task_id','task_type','instruction','reward')},indent=2)+'\n',encoding='utf-8')
    for name,content in (files or {}).items():
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    return folder

def number(name,instruction,computed,independent,reward):
    assert computed==independent,(name,computed,independent)
    add(name,'math',instruction+' Write only the integer result to answer.txt.',computed,reward)
    CHECKS.append(dict(task_id=name,kind='two_arithmetic_methods',passed=True,expected=computed))

def csv_text(header,rows):
    f=io.StringIO();writer=csv.writer(f,lineterminator='\n');writer.writerow(header);writer.writerows(rows);return f.getvalue()

def coding(name,instruction,reference,cases):
    broken='def solve(values):\n    return None\n'
    lines=['import unittest','from mylib import solve','class Tests(unittest.TestCase):','    def test_contract(self):']
    for inp,expected in cases:
        lines.append('        self.assertEqual(solve('+repr(inp)+'),'+repr(expected)+')')
    lines += ['        a=[3,1,3,2]; before=a[:]; solve(a); self.assertEqual(a,before)',"if __name__=='__main__':unittest.main()"]
    test='\n'.join(lines)+'\n'
    add(name,'coding',instruction+' Function name: solve(values). Do not mutate the input. Modify only mylib.py. Never change tests. Write DONE to answer.txt after tests pass.','tests_pass',3,{'mylib.py':broken,'test_contract.py':test})
    ref=DEST/'private_references'/name;ref.mkdir(parents=True);(ref/'reference.py').write_text(reference,encoding='utf-8')
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);(root/'test_contract.py').write_text(test,encoding='utf-8');codes=[]
        for source in (broken,reference):
            (root/'mylib.py').write_text(source,encoding='utf-8')
            p=subprocess.run([sys.executable,'-B','test_contract.py'],cwd=root,capture_output=True,timeout=5);codes.append(p.returncode)
        assert codes[0]!=0 and codes[1]==0,(name,codes,p.stderr)
    CHECKS.append(dict(task_id=name,kind='broken_fails_reference_passes',passed=True))

def main():
    if (DEST/'labels.json').exists():raise ValueError('Refuse overwrite completed fixture')
    number('math_divisible','How many integers from 1 to 275 inclusive are divisible by 4 or 9, counting each integer once?',sum(n%4==0 or n%9==0 for n in range(1,276)),275//4+275//9-275//36,5)
    number('math_coin_combinations','How many unordered combinations of coins of denominations 2,5,7 sum to 29? Unlimited coins of each denomination are available.',sum(2*a+5*b+7*c==29 for a in range(15) for b in range(6) for c in range(5)),9,4)
    ways=[1]+[0]*34
    for n in range(1,35):ways[n]=sum(ways[n-k] for k in (1,3,4) if n>=k)
    def recurrence(n,memo={0:1}):
        if n<0:return 0
        if n not in memo:memo[n]=sum(recurrence(n-k) for k in (1,3,4))
        return memo[n]
    number('math_stairs','A staircase has 34 steps. A move climbs 1,3,or4 steps. How many ordered sequences of moves land exactly at the top?',ways[34],recurrence(34),3)
    number('math_modular','Compute the remainder of 13 to the power 241 divided by 107.',pow(13,241,107),(13**241)%107,3)
    number('math_lattice','Count shortest lattice paths from (0,0) to (8,6), using only right and up steps, that never pass through (4,3).',math.comb(14,6)-math.comb(7,3)**2,1778,2)
    number('math_weighted','A shipment has 17 boxes of 24 screws and 13 boxes of 18 screws. Exactly 27 screws are damaged. How many usable screws remain?',17*24+13*18-27,615,2)
    rows=[('north','a',2,7),('south','b',5,3),('north','b',4,11),('west','a',3,5),('south','a',7,2),('west','c',6,13),('north','c',1,17),('south','c',8,19)]
    data={'records.csv':csv_text(['region','sku','qty','price'],rows)}
    specs=[('data_group_revenue','For each region sum qty*price over all its rows; return the largest regional total.',max(sum(q*p for reg,sku,q,p in rows if reg==r) for r in ('north','south','west')),181,5),
      ('data_filtered_median','Keep rows where qty>=3 and price<15. Return the median qty; average the middle two values when needed.',5,5,4),
      ('data_distinct','Count distinct sku values among rows whose region is north or west.',len({s for r,s,q,p in rows if r in ('north','west')}),3,3),
      ('data_weighted_floor','Compute sum(qty*price)/sum(qty) over all rows and round DOWN to the nearest integer.',sum(q*p for r,s,q,p in rows)//sum(q for r,s,q,p in rows),9,3),
      ('data_excluding','Sum qty for rows whose sku is not a and whose price is at least 10.',sum(q for r,s,q,p in rows if s!='a' and p>=10),19,2),
      ('data_second_largest','Sum qty by region, then return the second largest of the three region totals.',sorted([sum(q for r,s,q,p in rows if r==reg) for reg in ('north','south','west')])[-2],9,2)]
    for n,question,calc,manual,reward in specs:
        assert calc==manual,(n,calc,manual)
        add(n,'data_analysis','Read all rows of records.csv. '+question+' Write only the number to answer.txt.',manual,reward,data)
        CHECKS.append(dict(task_id=n,kind='aggregation_and_manual_check',expected=manual,passed=True))
    for i,(city,person) in enumerate([('Ulm','Ada Birch'),('Riga','Ivo Lake'),('Lund','Nora Fern'),('Bern','Ema Stone')]):
        name='search_chain_'+str(i)
        files={'kb/object.md':f'# Artifact {i}\ncurator: {person}\n','kb/person.md':f'# {person}\nemployer: Archive {i}\n','kb/place.md':f'# Archive {i}\ncity: {city}\n','kb/noise.md':'# Noise Archive\ncity: Oslo\n'}
        add(name,'search',f'Use only kb/. Return the city of the employer of the curator of Artifact {i}. Write only the exact city to answer.txt.',city,3,files)
        CHECKS.append(dict(task_id=name,kind='explicit_three_edge_chain',expected=city,passed=True))
    coding('coding_prefix','Return a list of running sums, including each current element.',
        'def solve(values):\n    result=[]; total=0\n    for x in values:\n        total+=x;result.append(total)\n    return result\n',
        [([],[]),([2,-3,7],[2,-1,6]),([0,0],[0,0])])
    coding('coding_runs','Return lengths of maximal strictly increasing consecutive runs, in their original order. Equal adjacent values begin a new run.',
        'def solve(values):\n    if not values:return []\n    result=[];n=1\n    for a,b in zip(values,values[1:]):\n        if b>a:n+=1\n        else:result.append(n);n=1\n    result.append(n)\n    return result\n',
        [([],[]),([1,3,2,4,5,5],[2,3,1]),([4,3,2],[1,1,1]),([2],[1])])
    coding('coding_histogram','Return sorted (value,count) pairs for the distinct integer values.',
        'def solve(values):\n    from collections import Counter\n    return sorted(Counter(values).items())\n',
        [([],[]),([3,1,3,-2,1],[(-2,1),(1,2),(3,2)]),([0,0],[(0,2)])])
    coding('coding_next_greater','For each position return the value of the nearest element strictly to its right that is greater than the current value, or None if absent.',
        'def solve(values):\n    out=[]\n    for i,x in enumerate(values):\n        out.append(next((y for y in values[i+1:] if y>x),None))\n    return out\n',
        [([],[]),([2,1,2,4,3],[4,2,4,None,None]),([3,3,3],[None,None,None]),([-3,-1,-2],[-1,None,None])])
    add('control_search_local','search','In which year was Alba born? Write only the final answer to answer.txt.','1987',2,{'kb/alba.md':'# Alba\nborn: 1987\n'})
    add('control_data_local','data_analysis',"How many units of product 'widget' were sold in months 5 through 6 inclusive? Write only the final answer to answer.txt.",'9',2,{'sales.csv':'product,month,units\nwidget,5,4\nwidget,6,5\nwidget,7,80\n'})
    add('control_data_missing','data_analysis','Read missing.csv and calculate total units. Do not invent missing data. Write the result to answer.txt.','UNSOLVABLE',3,unsolvable=True)
    add('control_math_contradiction','math','Find an integer x satisfying both x+9=21 and x+9=22. If none exists return UNSOLVABLE. Write the result to answer.txt.','UNSOLVABLE',3,unsolvable=True)
    assert len(LABELS)==24
    (DEST/'labels.json').write_text(json.dumps(LABELS,indent=2)+'\n',encoding='utf-8')
    report=dict(total=len(LABELS),solvable=sum(not x['unsolvable'] for x in LABELS.values()),max_score=sum(x['reward'] for x in LABELS.values() if not x['unsolvable']),checks=CHECKS,note='Author-generated new instances of familiar families, not a hidden organizer holdout; references never copied into task roots.')
    (DEST/'fixture_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
if __name__=='__main__':main()
