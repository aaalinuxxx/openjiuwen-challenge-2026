"""Freeze numeric join dev/holdout fixtures using a separate Decimal nested-loop oracle."""
import csv,json
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'experiments/E87_numeric_joins'
D=Decimal

def case(name,left,right,expected,*,join='inner',price_default='0',state=None,weighted=False,rounding=None,variant=0,split='dev'):
    return dict(name=name,left=left,right=right,expected=expected,join=join,price_default=price_default,state=state,weighted=weighted,rounding=rounding,variant=variant,split=split)

CASES=[
case('fractional_prices',[('A','2'),('B','3'),('C','1'),('D','4')],[('A','1.25','ok'),('B','2.40','ok'),('C','0.05','ok'),('D','3.15','ok')],'22.35'),
case('duplicate_pairs',[('A','2'),('A','3'),('B','1')],[('A','1.10','ok'),('A','2.20','ok'),('B','4.05','ok')],'20.55'),
case('unmatched_default',[('A','2'),('B','3'),('X','4')],[('A','1.25','ok'),('B','2.40','ok')],'19.70',join='left',price_default='2.50'),
case('empty_inner',[('X','2'),('Y','3')],[('A','1.25','ok'),('B','2.40','ok')],'0'),
case('string_keys',[('01','2'),('1','3'),('001','4'),('Z','9')],[('01','1.25','ok'),('1','2.50','ok'),('001','0.10','ok')],'10.40'),
case('filter_after_pairing',[('A','2'),('B','3'),('X','4')],[('A','1.25','ok'),('A','100','blocked'),('B','2.40','blocked')],'12.50',join='left',price_default='2.50',state='ok'),
case('beyond_preview',[('A','1'),('B','1'),('C','1'),('A','2'),('D','3')],[('A','0.10','ok'),('B','0.20','ok'),('C','0.30','ok'),('A','1.00','ok'),('D','2.50','ok')],'11.30'),
case('negative_quantities',[('A','-2'),('B','3'),('A','1')],[('A','1.25','ok'),('B','0.40','ok')],'-0.05'),
case('round_once',[('A','1'),('B','1'),('C','1')],[('A','0.005','ok'),('B','0.005','ok'),('C','0.005','ok')],'0.02',rounding=2),
case('weighted_average',[('A','2'),('A','1'),('B','3')],[('A','1.10','ok'),('A','2.20','ok'),('B','4.00','ok')],'2.43',weighted=True,rounding=2,variant=1),
case('hold_decimal_multiplicity',[('K','1.5'),('K','2.5'),('Q','2')],[('K','0.25','ok'),('K','0.75','ok'),('Q','1.125','ok')],'6.25',variant=1,split='holdout'),
case('hold_no_right_rows',[('K','2'),('Z','3')],[],'3.75',join='left',price_default='0.75',variant=1,split='holdout'),
case('hold_postfilter',[('K','2'),('Q','4'),('Z','1')],[('K','9','blocked'),('K','1.75','ok'),('Q','99','blocked')],'4',join='left',price_default='0.50',state='ok',variant=1,split='holdout'),
case('hold_negative_round',[('K','-3')],[('K','0.005','ok')],'-0.02',rounding=2,variant=1,split='holdout'),
case('hold_leading_zero',[('7','2'),('07','3'),('007','4')],[('7','0.25','ok'),('07','0.50','ok'),('007','0.75','ok')],'5',variant=1,split='holdout'),
case('hold_weighted',[('K','2'),('Q','1')],[('K','0.25','ok'),('K','1.25','ok'),('Q','2.00','ok')],'1.00',weighted=True,rounding=2,variant=1,split='holdout'),
]

def oracle(c):
    products=[];weights=[]
    for key,qty in c['left']:
        matches=[r for r in c['right'] if key==r[0]]
        if not matches and c['join']=='left':matches=[None]
        for row in matches:
            if row is not None and c['state'] and row[2]!=c['state']:continue
            price=D(c['price_default'] if row is None else row[1])
            products.append(D(qty)*price);weights.append(D(qty))
    result=sum(products,D(0))
    if c['weighted']:result/=sum(weights,D(0))
    if c['rounding'] is not None:result=result.quantize(D('0.01'),rounding=ROUND_HALF_UP)
    assert result==D(c['expected']),(c['name'],result,c['expected'])
    return str(result),len(products)

def instruction(c):
    if c['variant']==0:
        text='Read orders.csv and prices.csv. Match orders.sku to prices.code by exact string equality, preserving leading zeros. Each left row must be paired with EVERY matching right row; retain duplicates on both sides. '
    else:
        text='Calculate a scalar from orders.csv and prices.csv. Treat sku and code as text identifiers. For each order, enumerate all price records with an identical code; repeated records represent distinct matches. '
    if c['join']=='inner':text+='Discard orders that have no price match. '
    else:text+='If an order has no match in the original prices.csv, include it once with price '+c['price_default']+'. '
    if c['state']:text+="After forming the pairs, keep only pairs whose right state is '"+c['state']+"', plus unmatched orders. A matched order with only rejected states is NOT unmatched. "
    if c['weighted']:text+='Compute sum(qty * price) divided by sum(qty) over all retained pairs; repeat qty for each matching price row. '
    else:text+='Compute the sum of orders.qty multiplied by the price of each retained pair. The sum of zero pairs is 0. '
    text+='Use every CSV row, including rows after the previews. Quantities and prices may be signed decimals. '
    if c['rounding'] is not None:text+='Round only the final result to two decimal places using ROUND_HALF_UP. '
    else:text+='Return the exact decimal sum without rounding. '
    return text+'Write only the numeric result to answer.txt.'


def main():
    if ROOT.exists():raise ValueError('Refuse to overwrite existing fixtures')
    labels={'dev':{},'holdout':{}};validation=[]
    for c in CASES:
        answer,pairs=oracle(c);name=c['name'];folder=ROOT/c['split']/'tasks'/name;folder.mkdir(parents=True)
        truth=dict(task_id=name,task_type='data_analysis',instruction=instruction(c),reward=3,expected=c['expected'],unsolvable=False,group='E87_'+c['split'],comparison='decimal')
        labels[c['split']][name]=truth
        (folder/'task.json').write_text(json.dumps({k:truth[k] for k in ('task_id','task_type','instruction','reward')},indent=2)+'\n',encoding='utf-8')
        for filename,header,rows in [('orders.csv',['sku','qty'],c['left']),('prices.csv',['code','price','state'],c['right'])]:
            with (folder/filename).open('w',newline='',encoding='utf-8') as f:
                w=csv.writer(f);w.writerow(header);w.writerows(rows)
        validation.append(dict(task_id=name,split=c['split'],oracle=answer,hand_expected=c['expected'],retained_pairs=pairs,passed=True))
    for split,items in labels.items():
        (ROOT/split/'labels.json').write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(dev=len(labels['dev']),holdout=len(labels['holdout']),all_oracles_verified=True)))
if __name__=='__main__':main()
