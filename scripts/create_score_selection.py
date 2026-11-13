"""Freeze score-first release selection before any candidate response."""
import hashlib,json,math,shutil
from pathlib import Path
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'experiments/E130_score_selection'
def write(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if DEST.exists():raise ValueError('Refuse overwrite')
    labels={};checks=[]
    def add(name,kind,instruction,a,b,reward=3,files=None):
        assert str(a)==str(b),(name,a,b)
        row=dict(task_id=name,task_type=kind,instruction=instruction+' Write only the final answer to answer.txt.',reward=reward,expected=str(a),unsolvable=False,group='E130_new')
        if kind!='coding':row['comparison']='decimal'
        labels[name]=row;folder=DEST/'new_tasks'/name
        write(folder/'task.json',{k:row[k] for k in ('task_id','task_type','instruction','reward')})
        for n,s in (files or {}).items():
            p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
        checks.append(dict(task_id=name,expected=str(a),reference_agreement=True))
    add('hold_square_sum','math','Sum k squared for every integer k from 12 through 49 inclusive.',sum(k*k for k in range(12,50)),49*50*99//6-11*12*23//6,2)
    add('hold_weighted','math','Find the sum of k times (k+3) for k from 1 through 31 inclusive.',sum(k*(k+3) for k in range(1,32)),31*32*63//6+3*31*32//2,2)
    add('hold_divisibility','math','Count integers from 1 through 420 inclusive divisible by 4 or 7 but not both.',sum((n%4==0) != (n%7==0) for n in range(1,421)),420//4+420//7-2*(420//28))
    add('hold_crt','math','Find the smallest positive integer with remainder 4 modulo 9 and remainder 7 modulo 11.',next(n for n in range(1,100) if n%9==4 and n%11==7),(4*11*pow(11,-1,9)+7*9*pow(9,-1,11))%99)
    add('hold_factorial','math','How many trailing decimal zeros does 175 factorial have?',len(str(math.factorial(175)))-len(str(math.factorial(175)).rstrip('0')),175//5+175//25+175//125,2)
    add('hold_digit_sum','math','Find the sum of decimal digits of 3 to the power 65.',sum(map(int,str(3**65))),sum((3**65//10**i)%10 for i in range(40)),2)
    @lru_cache(None)
    def ways(n):return int(n==0) if n<=0 else ways(n-1)+ways(n-3)
    dp=[1]+[0]*19
    for n in range(1,20):dp[n]=sum(dp[n-k] for k in (1,3) if n>=k)
    add('hold_stairs','math','Count ordered sequences of moves of size 1 or 3 that sum to 19.',ways(19),dp[19])
    poly=[1]+[0]*26
    for coin in (3,5,8):
        for n in range(coin,27):poly[n]+=poly[n-coin]
    add('hold_coins','math','Count unordered ways to form 26 using unlimited coins with values 3, 5, and 8.',poly[26],sum(3*a+5*b+8*c==26 for a in range(10) for b in range(6) for c in range(4)))
    grid={}
    for x in range(9):
        for y in range(5):grid[x,y]=0 if (x,y)==(2,3) else (1 if (x,y)==(0,0) else grid.get((x-1,y),0)+grid.get((x,y-1),0))
    add('hold_grid','math','Count shortest paths from (0,0) to (8,4) using only right and up moves, avoiding (2,3).',grid[8,4],math.comb(12,4)-math.comb(5,2)*math.comb(7,1))
    add('hold_lcm','math','Find the smallest positive number divisible by 16, 24, and 35.',math.lcm(16,24,35),next(n for n in range(1,10000) if all(n%d==0 for d in (16,24,35))),2)
    weights=[2,5,3,7];values=[11,4,18,6]
    add('hold_weighted_mean','math','Take values 11, 4, 18, 6 with respective weights 2, 5, 3, 7. Find the floor of the weighted mean.',sum(v*w for v,w in zip(values,weights))//sum(weights),sum([v for v,w in zip(values,weights) for _ in range(w)])//sum(weights),2)
    add('hold_binomial','math','How many different 4-person committees can be chosen from 13 people?',math.comb(13,4),13*12*11*10//24,2)
    csv='kind,qty,price\na,7,4\nb,9,2\na,3,8\nc,5,6\na,6,3\n'
    add('hold_data_revenue','data_analysis','Using records.csv, sum qty*price for rows where kind is a.',70,7*4+3*8+6*3,4,{'records.csv':csv})
    add('hold_data_median','data_analysis','Using records.csv, compute the median qty among rows with price at least 4.',5,sorted([7,3,5])[1],3,{'records.csv':csv})
    for i,year in enumerate((1973,1981)):
        add('hold_search_'+str(i),'search','In which year was the architect of Tower '+str(i)+' born?',year,year,2,{'kb/tower.md':'Tower '+str(i)+' was designed by Mira '+str(i)+'.','kb/person.md':'Mira '+str(i)+' was born in '+str(year)+'.'})
    for name,fn,cases,reference in [('hold_code_runs','compress', [('', ''),('aaabbcaa','abca'),('abab','abab')],"''.join(c for i,c in enumerate(s) if i==0 or c!=s[i-1])"),('hold_code_sum','sum_even', [([],0),([1,2,4,7],6),([-2,-3,6],4)],'sum(x for x in s if x%2==0)')]:
        assert all(eval(reference,{'s':a})==b for a,b in cases)
        tests='import unittest\nfrom mylib import '+fn+'\nclass T(unittest.TestCase):\n    def test_all(self):\n'
        for a,b in cases:tests+='        self.assertEqual('+fn+'('+repr(a)+'),'+repr(b)+')\n'
        tests+='if __name__=="__main__":unittest.main()\n'
        add(name,'coding','Fix '+fn+' in mylib.py to satisfy test_contract.py. Return DONE when complete.','DONE','DONE',4,{'mylib.py':'def '+fn+'(s):\n    return None\n','test_contract.py':tests})
    write(DEST/'new_labels.json',labels);write(DEST/'reference_checks.json',checks)
    known={}
    for tasks,labs in [('experiments/E77_mixed_integration/tasks','experiments/E77_mixed_integration/labels.json'),('experiments/E122_compact_math/fresh_tasks','experiments/E122_compact_math/fresh_labels.json')]:
        for name,row in json.loads((ROOT/labs).read_text()).items():
            assert name not in known;known[name]=row;shutil.copytree(ROOT/tasks/name,DEST/'known_tasks'/name)
    write(DEST/'known_labels.json',known)
    sources=[p for p in (ROOT/'harness').rglob('*.py')]+[ROOT/n for n in ('run_agent.py','requirements.txt','scripts/score_selection_benchmark.py','scripts/frozen_benchmark.py','scripts/numeric_recheck_policy.py','scripts/terse_math_benchmark.py','scripts/create_score_selection.py','tests/test_score_selection.py')]
    sources += [p for p in DEST.rglob('*') if p.is_file()]
    hashes={p.relative_to(ROOT).as_posix():digest(p) for p in sources}
    schedule=[]
    for suite,budget,arms in [('known',3000,['baseline','terse','terse_recheck']),('new',800,['terse','terse_recheck','baseline']),('new',2000,['terse_recheck','baseline','terse'])]:
        for arm in arms:
            name=suite+'_'+str(budget)+'_'+arm;schedule.append(name)
            write(DEST/('plan_'+name+'.json'),dict(hypothesis='H04.37_SCORE_FIRST_SELECTION',arm=arm,tasks='experiments/E130_score_selection/'+suite+'_tasks',labels='experiments/E130_score_selection/'+suite+'_labels.json',profile='csv-roomy',ranking_policy='calibrated',budget=budget,max_calls=70,concurrency=1,output_prefix='E131_'+name,frozen_hashes=hashes))
    write(DEST/'design.json',dict(schedule=schedule,criterion='Maximize sum of score/max_score across the three equally weighted suite-budget cells; ties minimize summed actual token cost. No no-regression or zero-wrong-answer gate.',arms=['baseline','terse','terse_recheck'],limits='Input integrity, complete accounting and frozen policies mandatory. No task-id or dataset-id routing.',recheck='One extra call on numeric literal after terse math prompt; denied/truncated correction retains original; unknown cost stops; repeated constant retains original.',limitations='Small author-generated selection sets; same novel tasks at two budgets are not independent samples. No hidden-test guarantee.',known_tasks=len(known),new_tasks=len(labels)))
    print(json.dumps(dict(known=len(known),new=len(labels),plans=len(schedule))))
if __name__=='__main__':main()
