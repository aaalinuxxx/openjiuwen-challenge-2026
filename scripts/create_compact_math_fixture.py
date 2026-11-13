"""New math instances frozen before compact-prompt API results."""
import json,math,re
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'experiments/E122_compact_math'
LABELS={};CHECKS=[]
def add(name,question,a,b,reward=3,unsolvable=False):
    assert a==b,(name,a,b)
    question=re.sub(r'([a-zA-Z])(?=[0-9(])',r'\1 ',question)
    question=re.sub(r',(?=[a-zA-Z0-9])',', ',question)
    instruction=question+' Write only the final answer to answer.txt.'
    record=dict(task_id=name,task_type='math',instruction=instruction,reward=reward,expected=str(a),unsolvable=unsolvable,group='E122_new_math')
    if not unsolvable:record['comparison']='decimal'
    LABELS[name]=record;folder=DEST/'fresh_tasks'/name;folder.mkdir(parents=True)
    (folder/'task.json').write_text(json.dumps({k:record[k] for k in ('task_id','task_type','instruction','reward')},indent=2)+'\n',encoding='utf-8')
    CHECKS.append(dict(task_id=name,expected=str(a),independent_methods_agree=True))
def main():
    if (DEST/'fresh_tasks').exists():raise ValueError('Refuse overwrite')
    mods=[7,11,13];remainders=[3,8,5];prod=math.prod(mods)
    crt=sum(r*(prod//m)*pow(prod//m,-1,m) for r,m in zip(remainders,mods))%prod
    add('new_crt','Find the smallest positive integer x whose remainders modulo7,11,13 are3,8,5 respectively.',next(x for x in range(1,prod+1) if all(x%m==r for m,r in zip(mods,remainders))),crt)
    factorial=str(math.factorial(125));zeros=len(factorial)-len(factorial.rstrip('0'))
    add('new_trailing_zeros','How many trailing decimal zeros are in125 factorial?',zeros,sum(125//(5**k) for k in range(1,5)))
    n=2**123;total=0
    while n:total+=n%10;n//=10
    add('new_digit_sum','Find the sum of decimal digits of2 to the power123.',sum(map(int,str(2**123))),total,2)
    dp=[0]+[1000]*43
    for n in range(1,44):dp[n]=min((dp[n-c]+1 for c in (4,7,9) if n>=c),default=1000)
    add('new_min_coins','Using unlimited coins of values4,7,9, find the minimum number of coins summing to43.',dp[43],min(a+b+c for a in range(11) for b in range(7) for c in range(5) if 4*a+7*b+9*c==43))
    grid={}
    for x in range(8):
        for y in range(6):grid[x,y]=0 if (x,y)==(3,2) else (1 if (x,y)==(0,0) else grid.get((x-1,y),0)+grid.get((x,y-1),0))
    add('new_blocked_grid','Count shortest lattice paths from(0,0) to(7,5), moving only up or right, which avoid(3,2).',grid[7,5],math.comb(12,5)-math.comb(5,2)*math.comb(7,3))
    add('new_lcm','What is the smallest positive integer divisible by21,35,and45?',math.lcm(21,35,45),next(n for n in range(1,10000) if n%21==n%35==n%45==0),2)
    add('new_exactly_two','How many integers from1 through240 inclusive are divisible by exactly two of2,3,5?',sum(sum(n%d==0 for d in (2,3,5))==2 for n in range(1,241)),240//6+240//10+240//15-3*(240//30))
    add('new_squared_sum','Compute the sum of k squared for integers k from1 through37 inclusive.',sum(k*k for k in range(1,38)),37*38*75//6,2)
    poly=[1]+[0]*23
    for coin,bound in ((2,5),(3,4),(7,3)):
        nxt=[0]*24
        for t in range(24):
            for c in range(bound+1):
                if t+c*coin<24:nxt[t+c*coin]+=poly[t]
        poly=nxt
    add('new_bounded_coins','Count unordered combinations summing to23, using at most5 coins of value2, at most4 coins of value3, and at most3 coins of value7.',poly[23],sum(2*a+3*b+7*c==23 for a in range(6) for b in range(5) for c in range(4)))
    ways=[1]+[0]*22
    for n in range(1,23):ways[n]=sum(ways[n-k] for k in (2,5) if n>=k)
    @lru_cache(None)
    def f(n):return int(n==0) if n<=0 else f(n-2)+f(n-5)
    add('new_stair_moves','Climb a22-step staircase, each move covering exactly2 or5 steps. Count ordered sequences ending exactly on step22.',ways[22],f(22))
    add('new_parity_conflict','Find an integer n which is simultaneously even and odd. If no such integer exists, return UNSOLVABLE.','UNSOLVABLE','UNSOLVABLE',unsolvable=True)
    add('new_integer_conflict','Find an integer n satisfying4*n=3. If no such integer exists, return UNSOLVABLE.','UNSOLVABLE','UNSOLVABLE',unsolvable=True)
    assert len(LABELS)==12
    (DEST/'fresh_labels.json').write_text(json.dumps(LABELS,indent=2)+'\n',encoding='utf-8')
    report=dict(total=12,solvable=10,max_score=sum(r['reward'] for r in LABELS.values() if not r['unsolvable']),checks=CHECKS,note='Independent algorithms cross-check numeric references; two impossibility controls. Author-generated familiar math families, not organizer hidden data.')
    (DEST/'fresh_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
if __name__=='__main__':main()
