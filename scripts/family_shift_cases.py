"""Prospective family-shift challenge. Never imports production solvers to build labels."""
import argparse
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'experiments'/'E41_family_shift'
TAIL = ' Write only the final answer to answer.txt.'
CASES = []

def add(task_id, task_type, instruction, answer, files=None, proof='', reference=None, impossible=False):
    CASES.append(dict(task_id=task_id, task_type=task_type, instruction=instruction,
        expected=str(answer), unsolvable=impossible, reward=3, files=files or {},
        oracle_evidence=proof, reference=reference))

add('math_paraphrase', 'math', 'There are 47 books on a shelf. Add 13 books, then remove 9. How many remain?'+TAIL,
    47+13-9, proof='Integer inventory: 47 + 13 - 9 = 51.')
add('math_percentage', 'math', 'A coat costs 200 units. A discount is 15 percent of the original price. What is the final price? Return an integer.'+TAIL,
    200*(100-15)//100, proof='200 * 85 / 100 = 170.')
add('math_gcd', 'math', 'Find the greatest positive integer that divides both 84 and 126.'+TAIL,
    math.gcd(84,126), proof='Euclidean algorithm: gcd(84,126)=42.')
add('math_sum', 'math', 'Compute the sum of all integers from 1 to 20 inclusive.'+TAIL,
    sum(range(1,21)), proof='20 * 21 / 2 = 210.')
add('math_zero_warning', 'math', 'Do not divide by 0; this is only a warning, not an operation. Compute 6 times 7.'+TAIL,
    6*7, proof='The only requested operation is multiplication: 42.')
add('math_zero_operation', 'math', 'A warehouse starts with 9 boxes. It is split equally into 0 warehouses. How many boxes does each warehouse have?'+TAIL,
    'UNSOLVABLE', proof='Explicit division of nonzero inventory by zero.', impossible=True)

sales = 'client,category,units,price,month\nA,red,2,10,1\nB,blue,4,5,1\nA,red,3,6,2\nC,red,1,20,3\nD,red,4,8,2\n'
data = list(csv.DictReader(io.StringIO(sales)))
weighted = sum(Fraction(r['price'])*int(r['units']) for r in data)/sum(int(r['units']) for r in data)
add('data_weighted_mean','data_analysis',
    'Using sales.csv, calculate the average price weighted by units over ALL rows. Return exactly two decimal places.'+TAIL,
    f'{float(weighted):.2f}', {'sales.csv':sales}, proof='Weighted sum 110; units 14; rounded to two decimals = 7.86.')
clients = {r['client'] for r in data if r['category']=='red' and int(r['month'])<=2}
add('data_distinct','data_analysis',
    'Using sales.csv, count DISTINCT clients with category red and month at most 2.'+TAIL,
    len(clients), {'sales.csv':sales}, proof='Distinct clients A,D: 2.')
values=sorted(int(r['units']) for r in data if r['category']=='red')
median=Fraction(values[1]+values[2],2)
add('data_filtered_median','data_analysis',
    'Using sales.csv, calculate the median units among category red rows. Return one decimal place.'+TAIL,
    f'{float(median):.1f}', {'sales.csv':sales}, proof='Sorted red units: 1,2,3,4; median 2.5.')
add('data_empty_count','data_analysis',
    'Using sales.csv, count rows whose category is green. An empty selection has count 0.'+TAIL,
    sum(r['category']=='green' for r in data), {'sales.csv':sales}, proof='No category green: 0.')
orders='sku,qty\nx,2\ny,3\nx,1\n'
prices='sku,price\nx,7\ny,4\n'
price_map={r['sku']:int(r['price']) for r in csv.DictReader(io.StringIO(prices))}
revenue=sum(int(r['qty'])*price_map[r['sku']] for r in csv.DictReader(io.StringIO(orders)))
add('data_two_file_join','data_analysis',
    'Join orders.csv with prices.csv on sku. Compute total qty times price over all orders. Return an integer.'+TAIL,
    revenue, {'orders.csv':orders,'prices.csv':prices}, proof='2*7 + 3*4 + 1*7 = 33.')
add('data_missing_source','data_analysis',
    "How many units of product 'widget' were sold in months 1 through 2 inclusive? Use only sales.csv. It is absent and no other data exists."+TAIL,
    'UNSOLVABLE', proof='Required source file is absent.', impossible=True)

kb={'kb/a.md':'# Mira Vale\nBorn: 1990\nMentor: Oren Pike\n',
    'kb/b.md':'# Oren Pike\nEmployer: Luma Labs\n',
    'kb/c.md':'# Luma Labs\nHeadquarters: Riga\nFounded: 2004\n',
    'kb/d.md':'# Mira Valen\nBorn: 1987\nEmployer: Other Corp\n',
    'kb/e.md':'# Other Corp\nHeadquarters: Porto\n'}
add('search_three_hop','search',
    "In which city is the headquarters of Mira Vale's mentor's employer?"+TAIL,
    'Riga',kb,proof='Mira Vale -> Mentor Oren Pike -> Employer Luma Labs -> Headquarters Riga.')
add('search_paraphrase_chain','search',
    'Use only kb/. Identify the company employing the mentor of Mira Vale and return its headquarters city.'+TAIL,
    'Riga',kb,proof='Same three-edge path; phrasing differs.')
conflict={'kb/a.md':'# Nia Moss\nBorn: 1980\nEmployer: Delta Works\n',
          'kb/b.md':'# Nia Moss\nBorn: 1981\nEmployer: Delta Works\n',
          'kb/c.md':'# Delta Works\nHeadquarters: Bern\n'}
add('search_irrelevant_conflict','search',
    "In which city is the headquarters of Nia Moss's employer? The conflicting birth year is irrelevant; use the agreed employer."+TAIL,
    'Bern',conflict,proof='Both cards agree on employer Delta Works; headquarters Bern.')
founder={'kb/a.md':'# Sol Materials\nFounder: Elin Wood\n',
         'kb/b.md':'# Elin Wood\nBorn: 1977\n'}
add('search_new_relation','search',
    'Use only kb/. What is the birth year of the founder of Sol Materials?'+TAIL,
    '1977',founder,proof='Sol Materials -> Founder Elin Wood -> Born 1977.')
add('search_absent','search','In which year was Zora Cloud born? Use only kb/.'+TAIL,
    'UNSOLVABLE',kb,proof='Zora Cloud has no record; closed KB.',impossible=True)
add('search_conflicting_fact','search',
    'Use only kb/. In which year was Nia Moss born? There is no preferred source; return UNSOLVABLE if the year cannot be uniquely determined.'+TAIL,
    'UNSOLVABLE',conflict,proof='Two equally authoritative birth years, 1980 and 1981.',impossible=True)

def test_file(body):
    return 'import unittest\nimport mylib\n\nclass Checks(unittest.TestCase):\n'+body+"\nif __name__ == '__main__': unittest.main()\n"

def coding(name,instruction,buggy,reference,body,extra=None,impossible=False,proof='Reference implementation passes; initial implementation fails.'):
    files={'mylib.py':buggy,'test_mylib.py':test_file(body)}
    files.update(extra or {})
    add(name,'coding',instruction+' Do not change tests. Write DONE to answer.txt only after all tests pass.',
        'UNSOLVABLE' if impossible else 'tests_pass',files,proof,reference,impossible)

coding('coding_intervals',
    'Fix merge_intervals. Merge overlapping OR touching intervals, sort output by start, and do not mutate the input.',
    'def merge_intervals(intervals):\n    return sorted(intervals)\n',
    {'mylib.py':'''def merge_intervals(intervals):
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
    return out
'''},
    '''    def test_touch(self): self.assertEqual(mylib.merge_intervals([(3,5),(1,3),(8,9)]), [(1,5),(8,9)])
    def test_nested(self): self.assertEqual(mylib.merge_intervals([(1,9),(2,3)]), [(1,9)])
    def test_empty(self): self.assertEqual(mylib.merge_intervals([]), [])
    def test_input(self):
        data = [(5,7),(1,2)]
        before = list(data)
        mylib.merge_intervals(data)
        self.assertEqual(data, before)
''')

coding('coding_brackets',
    'Fix balanced(s): match (), [] and {} with correct nesting. Ignore other characters.',
    "def balanced(s):\n    return s.count('(') == s.count(')')\n",
    {'mylib.py':'''def balanced(s):
    stack = []
    pairs = {')':'(', ']':'[', '}':'{'}
    for c in s:
        if c in '([{':
            stack.append(c)
        elif c in pairs:
            if not stack or stack.pop() != pairs[c]:
                return False
    return not stack
'''},
    '''    def test_nested(self): self.assertTrue(mylib.balanced('a{b[c(d)]}'))
    def test_crossed(self): self.assertFalse(mylib.balanced('([)]'))
    def test_unclosed(self): self.assertFalse(mylib.balanced('['))
    def test_extra(self): self.assertFalse(mylib.balanced(']'))
    def test_empty(self): self.assertTrue(mylib.balanced(''))
''')

coding('coding_overlap',
    'Fix occurrences(text, pattern). Count overlapping exact matches. Empty pattern returns 0.',
    'def occurrences(text, pattern):\n    return text.count(pattern)\n',
    {'mylib.py':'''def occurrences(text, pattern):
    if not pattern:
        return 0
    return sum(text.startswith(pattern, i) for i in range(len(text)-len(pattern)+1))
'''},
    '''    def test_overlap(self): self.assertEqual(mylib.occurrences('aaaa','aa'), 3)
    def test_empty(self): self.assertEqual(mylib.occurrences('abc',''), 0)
    def test_missing(self): self.assertEqual(mylib.occurrences('ab','abcd'), 0)
    def test_exact(self): self.assertEqual(mylib.occurrences('abc','abc'), 1)
''')

coding('coding_multimodule',
    'Fix mylib.py: keep values at least the threshold returned by settings.threshold(). Preserve that imported function. Do not edit a_settings.py.',
    'from a_settings import threshold\ndef keep(values):\n    return [v for v in values if v > threshold()]\n',
    {'mylib.py':'from a_settings import threshold\ndef keep(values):\n    return [v for v in values if v >= threshold()]\n'},
    '''    def test_edge(self): self.assertEqual(mylib.keep([4,5,6]), [5,6])
    def test_empty(self): self.assertEqual(mylib.keep([]), [])
    def test_import(self):
        import a_settings
        self.assertEqual(a_settings.threshold(), 5)
        self.assertIs(mylib.threshold, a_settings.threshold)
''',
    {'a_settings.py':'def threshold():\n    return 5\n'})

coding('coding_stateful',
    'Fix Counter. It starts at zero; next() increments and returns its own state. Each instance is independent.',
    'class Counter:\n    def __init__(self): self.value = 0\n    def next(self): return 1\n',
    {'mylib.py':'class Counter:\n    def __init__(self): self.value = 0\n    def next(self):\n        self.value += 1\n        return self.value\n'},
    '''    def test_sequence(self):
        c = mylib.Counter()
        self.assertEqual(c.next(), 1)
        self.assertEqual(c.next(), 2)
    def test_independent(self):
        a, b = mylib.Counter(), mylib.Counter()
        a.next()
        self.assertEqual(b.next(), 1)
''')

coding('coding_pure_conflict',
    'Implement deterministic pure f(x). It must depend only on x: no state, call-order or test introspection. Both assertions on f(7) are required.',
    'def f(x):\n    return 0\n',None,
    '''    def test_first(self): self.assertEqual(mylib.f(7), 3)
    def test_second(self): self.assertEqual(mylib.f(7), 4)
''',impossible=True,proof='For deterministic pure f and the same input 7, f(7)=3 and f(7)=4 contradict.')

def validate_case(case):
    if case['task_type'] != 'coding':
        return dict(task_id=case['task_id'], valid=True, evidence=case['oracle_evidence'])
    with tempfile.TemporaryDirectory(prefix='oj-e41-oracle-') as tmp:
        work=Path(tmp)
        for name,content in case['files'].items():
            dest=work/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(content,encoding='utf-8')
        def run():
            return subprocess.run([sys.executable,'-B','test_mylib.py'],cwd=work,capture_output=True,timeout=8).returncode
        assert run()!=0, 'Initial coding task must fail'
        if case['unsolvable']:
            assert case['task_id']=='coding_pure_conflict'
            return dict(task_id=case['task_id'],valid=True,method='logical contradiction under explicit purity',evidence=case['oracle_evidence'])
        for name,content in case['reference'].items():
            (work/name).write_text(content,encoding='utf-8')
        assert run()==0, 'Reference must pass'
        return dict(task_id=case['task_id'],valid=True,method='reference passes original tests; initial code fails')

def prepare():
    if FIXTURE.exists(): raise ValueError('Frozen fixture already exists; never overwrite')
    validation=[validate_case(c) for c in CASES]
    FIXTURE.mkdir(parents=True)
    for case in CASES:
        folder=FIXTURE/'tasks'/case['task_id']
        folder.mkdir(parents=True)
        public={k:v for k,v in case.items() if k not in ('files','oracle_evidence','reference')}
        (folder/'task.json').write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf-8')
        for name,content in case['files'].items():
            p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding='utf-8')
    hashes={p.relative_to(FIXTURE/'tasks').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (FIXTURE/'tasks').rglob('*') if p.is_file()}
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),baseline_commit='8823e525e5c5d02be468738ed2c0a7ebdb5d44a2',
        scope='prospective authored family-shift/edge-case challenge; not external blind or representative holdout',
        hypotheses=['H00.2','H02','H05.3'],total=len(CASES),solvable=sum(not c['unsolvable'] for c in CASES),
        fixtures_sha256=hashes,validation=validation,
        oracle_evidence={c['task_id']:c['oracle_evidence'] for c in CASES},
        coding_references={c['task_id']:c['reference'] for c in CASES if c['reference']},
        plan=dict(order=['offline all 24 on frozen production code','live noncoding (18 tasks, budget<=3000, calls<=12)',
                         'live coding (6 tasks, budget<=2000, calls<=6)'],
            total_live_budget_cap=5000,total_live_calls_cap=18,no_automatic_retries=True,
            stop_on_unknown_cost=True,metrics=['verified solutions','score','wrong submissions','false refusals','truncations','API usage'],
            acceptance='No false positive UNSOLVABLE/SKIPPED on solvable tasks; zero wrong submitted answers. Coverage reported, not assumed.',
            data_policy='Never tune then present reuse as independent; any later replay of this suite is dev.'))
    (FIXTURE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(total=len(CASES),solvable=manifest['solvable'],coding_references_checked=5,api_calls=0)))
    print(FIXTURE)

if __name__=='__main__':
    prepare()
