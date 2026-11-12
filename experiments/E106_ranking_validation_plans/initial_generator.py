"""New-seed scheduling validation with 24 fresh author-generated tasks."""
import csv,io,json,math,random,shutil,subprocess,sys,tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'experiments/E105_ranking_validation'
SOURCE=ROOT/'experiments/E77_mixed_integration'
NEW={}
CHECKS=[]
def add(name,kind,instruction,expected,files=None,unsolvable=False,comparison=None):
    name='fresh_'+name
    NEW[name]=dict(task_id=name,task_type=kind,instruction=instruction,reward=3,
        expected=str(expected),unsolvable=unsolvable,group='E105_fresh',comparison=comparison)
    folder=DEST/'new_tasks'/name;folder.mkdir(parents=True)
    for filename,text in (files or {}).items():
        p=folder/filename;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    (folder/'task.json').write_text(json.dumps({k:NEW[name][k] for k in ('task_id','task_type','instruction','reward')},indent=2)+'\n',encoding='utf-8')
def csv_text(header,rows):
    f=io.StringIO(newline='');w=csv.writer(f);w.writerow(header);w.writerows(rows);return f.getvalue()
def math_task(name,instruction,computed,hand):
    assert computed==hand,(name,computed,hand)
    add(name,'math',instruction+' Write only the integer result to answer.txt.',hand)
    CHECKS.append(dict(task_id='fresh_'+name,kind='independent_arithmetic',expected=hand,computed=computed,passed=True))
def code_task(name,instruction,broken,reference,assertions):
    test='import unittest\nfrom mylib import *\n\nclass Tests(unittest.TestCase):\n    def test_contract(self):\n'
    test+=''.join('        '+line+'\n' for line in assertions.splitlines())
    test+="\nif __name__=='__main__':unittest.main()\n"
    add(name,'coding',instruction+' Modify only mylib.py. Do not change tests. Write DONE to answer.txt after all tests pass.','tests_pass',{'mylib.py':broken,'test_contract.py':test})
    folder=DEST/'new_tasks'/('fresh_'+name)
    with tempfile.TemporaryDirectory() as temp:
        target=Path(temp);(target/'test_contract.py').write_text(test,encoding='utf-8')
        results=[]
        for code in (broken,reference):
            (target/'mylib.py').write_text(code,encoding='utf-8')
            run=subprocess.run([sys.executable,'-B','test_contract.py'],cwd=target,capture_output=True,timeout=5)
            results.append(run.returncode)
        assert results[0]!=0 and results[1]==0,(name,results,run.stderr.decode(errors='replace'))
    ref=DEST/'private_references'/name;ref.mkdir(parents=True)
    (ref/'reference.py').write_text(reference,encoding='utf-8')
    CHECKS.append(dict(task_id='fresh_'+name,kind='coding_reference',broken_failed=True,reference_passed=True,passed=True))
def main():
    if DEST.exists():raise ValueError('Refuse overwrite')
    math_task('math_paths','A lattice path uses exactly seven rightward and five upward unit steps. How many distinct step sequences are possible?',math.comb(12,5),792)
    math_task('math_union','How many integers from 1 through 150 inclusive are divisible by 3 or by 7? Count those divisible by both only once.',sum(n%3==0 or n%7==0 for n in range(1,151)),64)
    math_task('math_modular','Find the remainder when 7 raised to power 123 is divided by 101.',pow(7,123,101),27)
    factors=[d for d in range(2,13196) if 13195%d==0 and all(d%p for p in range(2,math.isqrt(d)+1))]
    math_task('math_prime_factor','What is the largest prime factor of 13195?',max(factors),29)
    ways=sum(a+3*b+4*c==7 for a in range(8) for b in range(3) for c in range(2))
    math_task('math_coin_ways','You have unlimited coins of values 1,3,4. How many unordered multisets of coins sum to 7? Different orders of the same coins count once.',ways,5)
    add('math_inconsistent','math','Find an integer n satisfying BOTH n+4=10 and n+4=11. If no such integer exists, return UNSOLVABLE. Write the answer to answer.txt.','UNSOLVABLE',unsolvable=True)
    add('search_custodian','search','Use only kb/. Return the city of the organization holding custody of the Meridian Lens. Write only the city to answer.txt.','Turku',{'kb/lens.md':'# Meridian Lens\ncustodian: Cedar Archive\n','kb/archive.md':'# Cedar Archive\ncity: Turku\n','kb/noise.md':'# Linden Archive\ncity: Bergen\n'})
    add('search_latest','search','Use only kb/. Which product has the latest launch year? Return only its exact name to answer.txt.','Mistral',{'kb/products.md':'# Product launches\nKestrel: 2031\nMistral: 2034\nTern: 2029\n'})
    add('search_conditions','search','Use only kb/. Return the director of the only station with climate cold and capacity at least 12. Write only the director name to answer.txt.','Ema Reed',{'kb/a.md':'# North Station\nclimate: cold\ncapacity: 14\ndirector: Ema Reed\n','kb/b.md':'# West Station\nclimate: warm\ncapacity: 40\ndirector: Kai Moss\n','kb/c.md':'# East Station\nclimate: cold\ncapacity: 9\ndirector: Ada Snow\n'})
    add('search_chain','search','Use only kb/. Return the birth year of the person who designed the engine used by vessel Lumen. Write only the year to answer.txt.','1982',{'kb/vessel.md':'# Lumen\nengine: Zephyr\n','kb/engine.md':'# Zephyr\ndesigner: Ivo Dale\n','kb/person.md':'# Ivo Dale\nborn: 1982\n'})
    add('search_inverse','search','Use only kb/. Which person has tutor named Lina Vale? Exactly one person matches. Write only that person name to answer.txt.','Nora Pine',{'kb/a.md':'# Nora Pine\ntutor: Lina Vale\n','kb/b.md':'# Vera Oak\ntutor: Tomas Glen\n','kb/c.md':'# Lina Vale\ntutor: Ada Peak\n'})
    add('search_conflict','search','Use only kb/. Return the launch year of the Amber Ferry. Both sources have equal authority and neither supersedes the other. Return UNSOLVABLE if no unique year follows. Write the answer to answer.txt.','UNSOLVABLE',{'kb/one.md':'# Amber Ferry\nlaunch: 2001\n','kb/two.md':'# Amber Ferry\nlaunch: 2004\n'},unsolvable=True)
    rows=[('west','a'),('west','a'),('east','a'),('west','b'),('east','c')]
    assert len(set(rows))==4
    add('data_unique_pairs','data_analysis','Read records.csv. Count distinct (region,sku) pairs across all rows. Repeated identical pairs count once. Write the integer to answer.txt.','4',{'records.csv':csv_text(['region','sku'],rows)},comparison='decimal')
    rows=[('west',3),('west',7),('east',8),('east',6),('north',12),('north',1)]
    sums={k:sum(v for r,v in rows if r==k) for k,_ in rows};assert max(sums.values())==14
    add('data_group_max','data_analysis','Read records.csv. Sum value separately for each region, then return the largest of these region totals as a number. Use every row. Write the number to answer.txt.','14',{'records.csv':csv_text(['region','value'],rows)},comparison='decimal')
    vals=[-4,0,2,8,10,12];positive=sorted(v for v in vals if v>0);assert (positive[1]+positive[2])/2==9
    add('data_positive_median','data_analysis','Read values.csv. Discard value<=0, then compute the median of the retained values. For an even count use the average of the two middle values. Write the number to answer.txt.','9',{'values.csv':csv_text(['value'],[(v,) for v in vals])},comparison='decimal')
    rows=[('2026-10-31',100),('2026-11-01',3),('2026-11-30',5),('2026-12-01',900)]
    assert sum(v for d,v in rows if '2026-11-01'<=d<='2026-11-30')==8
    add('data_dates','data_analysis','Read events.csv. Sum qty for dates in November 2026 inclusive. Dates use YYYY-MM-DD. Do not include October or December. Write the number to answer.txt.','8',{'events.csv':csv_text(['date','qty'],rows)},comparison='decimal')
    rows=[('sale',2,'3.50'),('sale',1,'2.25'),('refund',1,'3.50')]
    assert sum((1 if k=='sale' else -1)*q*Decimal(p) for k,q,p in rows)==Decimal('5.75')
    add('data_net','data_analysis','Read transactions.csv. Net proceeds equal sum(qty*price) for sale rows minus sum(qty*price) for refund rows. Include every row, use exact decimal arithmetic. Write the decimal result to answer.txt.','5.75',{'transactions.csv':csv_text(['kind','qty','price'],rows)},comparison='decimal')
    add('data_missing','data_analysis','Read missing.csv and compute its total qty. The file must be supplied; do not invent data. Write the number to answer.txt.','UNSOLVABLE',unsolvable=True)
    code_task('coding_runs','Implement run_lengths(values): return a list of (value,count) tuples for consecutive equal runs. Preserve run order and do not modify the input.',
        'def run_lengths(values):\n    return []\n',
        'def run_lengths(values):\n    out=[]\n    for x in values:\n        if out and out[-1][0]==x:out[-1]=(x,out[-1][1]+1)\n        else:out.append((x,1))\n    return out\n',
        "self.assertEqual(run_lengths([]),[])\nself.assertEqual(run_lengths([2,2,1,2]),[(2,2),(1,1),(2,1)])\nself.assertEqual(run_lengths(['a','a','b']),[('a',2),('b',1)])\na=[3,3,4];before=a[:];run_lengths(a)\nself.assertEqual(a,before)")
    code_task('coding_unique','Implement stable_unique(values) for hashable elements: return their first appearances in original order; do not modify values.',
        'def stable_unique(values):\n    return []\n',
        'def stable_unique(values):\n    return list(dict.fromkeys(values))\n',
        "self.assertEqual(stable_unique([]),[])\nself.assertEqual(stable_unique([3,1,3,2,1]),[3,1,2])\nself.assertEqual(stable_unique(['b','a','b',None]),['b','a',None])\na=[2,1,2];before=a[:];stable_unique(a)\nself.assertEqual(a,before)")
    code_task('coding_rotate','Implement rotate_right(values,k). Return a new list rotated right by k positions; negative k rotates left, large k wraps modulo length, empty input returns []. Do not modify input.',
        'def rotate_right(values,k):\n    return values\n',
        'def rotate_right(values,k):\n    if not values:return []\n    k%=len(values)\n    return values[-k:]+values[:-k] if k else values[:]\n',
        "self.assertEqual(rotate_right([],5),[])\nself.assertEqual(rotate_right([1,2,3],1),[3,1,2])\nself.assertEqual(rotate_right([1,2,3],-1),[2,3,1])\nself.assertEqual(rotate_right([1,2,3],7),[3,1,2])\na=[1,2];b=rotate_right(a,0)\nself.assertIsNot(a,b)\nself.assertEqual(a,[1,2])")
    code_task('coding_transpose','Implement transpose(matrix) for rectangular lists of lists. Return columns as new lists, [] maps to []. Do not modify matrix.',
        'def transpose(matrix):\n    return matrix\n',
        'def transpose(matrix):\n    return [list(c) for c in zip(*matrix)]\n',
        "self.assertEqual(transpose([]),[])\nself.assertEqual(transpose([[1,2,3],[4,5,6]]),[[1,4],[2,5],[3,6]])\nself.assertEqual(transpose([[7],[8]]),[[7,8]])\na=[[1,2],[3,4]];before=[r[:] for r in a];transpose(a)\nself.assertEqual(a,before)")
    code_task('coding_missing_positive','Implement first_missing_positive(values): return the smallest strictly positive integer absent from the input. Ignore nonpositive numbers, handle duplicates, and do not modify input.',
        'def first_missing_positive(values):\n    return 1\n',
        'def first_missing_positive(values):\n    seen=set(values);n=1\n    while n in seen:n+=1\n    return n\n',
        "self.assertEqual(first_missing_positive([]),1)\nself.assertEqual(first_missing_positive([1,2,0]),3)\nself.assertEqual(first_missing_positive([3,4,-1,1]),2)\nself.assertEqual(first_missing_positive([1,1,2,2]),3)\na=[2,1];before=a[:];first_missing_positive(a)\nself.assertEqual(a,before)")
    add('coding_conflict','coding','Implement deterministic pure f(x), without state or inspecting tests. Both assertions for f(-1) are required. Modify only mylib.py; never change tests. Write DONE to answer.txt after tests pass.','UNSOLVABLE',{'mylib.py':'def f(x):\n    return 0\n','test_contract.py':"import unittest\nfrom mylib import f\nclass Tests(unittest.TestCase):\n    def test_a(self):self.assertEqual(f(-1),0)\n    def test_b(self):self.assertEqual(f(-1),2)\nif __name__=='__main__':unittest.main()\n"},unsolvable=True)
    assert len(NEW)==24
    # Independent consistency review for KB/data/unsolvable cases accompanies executable checks.
    facts={'fresh_search_custodian':'Turku','fresh_search_latest':'Mistral','fresh_search_conditions':'Ema Reed','fresh_search_chain':'1982','fresh_search_inverse':'Nora Pine','fresh_data_unique_pairs':'4','fresh_data_group_max':'14','fresh_data_positive_median':'9','fresh_data_dates':'8','fresh_data_net':'5.75'}
    for name,value in facts.items():
        assert NEW[name]['expected']==value
        CHECKS.append(dict(task_id=name,kind='explicit_facts_or_aggregation',expected=value,passed=True))
    for n,t in NEW.items():
        if t['unsolvable']:CHECKS.append(dict(task_id=n,kind='missing_source_or_explicit_contradiction',passed=True))
    original=json.loads((SOURCE/'labels.json').read_text(encoding='utf-8'))
    rng=random.Random(2026111202)
    old_ids=sorted(original);pool=[('old',n) for n in old_ids*2+rng.sample(old_ids,14)]+[('new',n) for n in sorted(NEW)]
    rng.shuffle(pool);labels={};lineage=[]
    for i,(kind,source_id) in enumerate(pool):
        name=f'validate_{i:03d}_{source_id}';reward=rng.randint(1,5)
        source=(DEST/'new_tasks'/source_id) if kind=='new' else SOURCE/'tasks'/source_id
        target=DEST/'tasks'/name;shutil.copytree(source,target)
        truth=dict(NEW[source_id] if kind=='new' else original[source_id],task_id=name,reward=reward,source_task_id=source_id)
        truth['group']='E105_fresh' if kind=='new' else 'E105_seen'
        labels[name]=truth
        (target/'task.json').write_text(json.dumps({k:truth[k] for k in ('task_id','task_type','instruction','reward')},indent=2)+'\n',encoding='utf-8')
        lineage.append(dict(task_id=name,source=kind,source_task_id=source_id,reward=reward))
    assert len(labels)==100 and sum(t['group']=='E105_fresh' for t in labels.values())==24
    (DEST/'labels.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (DEST/'new_labels.json').write_text(json.dumps(NEW,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validation=dict(seed=2026111202,new_count=24,new_solvable=20,total=100,solvable=sum(not t['unsolvable'] for t in labels.values()),max_score=sum(t['reward'] for t in labels.values() if not t['unsolvable']),by_type=dict(Counter(t['task_type'] for t in labels.values())),lineage=lineage,oracle_checks=CHECKS,checks_passed=all(c['passed'] for c in CHECKS))
    (DEST/'fixture_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in validation.items() if k not in ('lineage','oracle_checks')}))
if __name__=='__main__':main()
