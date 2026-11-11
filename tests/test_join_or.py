import copy
import csv
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from harness.agents.join_or import execute_join_or_plan,parse_join_or_scope,join_or_route,solve_join_or_task
from harness.agents.base_harness import solve_task
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker

TEXT="Read a.csv and b.csv. Left join a.key to b.code using exact string keys. Sum a.value for all resulting pairs where b.state equals 'yes' OR there is no matching right row. Preserve every matching pair, including duplicates. Print the exact sum."
PLAN=dict(left='a.csv',right='b.csv',left_key='key',right_key='code',join='left',
          filter=dict(op='eq_or_unmatched',side='right',column='state',equals='yes'),
          aggregate=dict(op='sum',side='left',column='value'))

class JoinOrExecutionControls(unittest.TestCase):
    def invoke(self,left,right,plan=None,max_pairs=1000000):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'a.csv').write_text(left)
            (root/'b.csv').write_text(right)
            return execute_join_or_plan(PLAN if plan is None else plan,list(root.glob('*.csv')),max_pairs=max_pairs)

    def test_duplicates_and_unmatched_and_blocked(self):
        result=self.invoke('key,value\nx,3\nx,2\ny,100\nz,7\n','code,state\nx,yes\nx,no\nx,yes\ny,no\n')
        self.assertEqual(result,'17')

    def test_blank_field_is_not_absent_row(self):
        left='key,value\nx,3\ny,7\n';right='code,state\nx,\n'
        self.assertEqual(self.invoke(left,right),'7')
        plan=copy.deepcopy(PLAN);plan['filter']['equals']=''
        self.assertEqual(self.invoke(left,right,plan),'10')

    def test_empty_tables_and_exact_signed_decimals(self):
        self.assertEqual(self.invoke('key,value\nx,0.10\nx,-0.03\ny,0.20\n','code,state\nx,yes\nx,yes\n'),'0.34')
        self.assertEqual(self.invoke('key,value\nx,3\ny,-1\n','code,state\n'),'2')
        self.assertEqual(self.invoke('key,value\n','code,state\nx,yes\n'),'0')

    def test_pair_limit_and_strict_predicate(self):
        left='key,value\nx,3\n';right='code,state\nx,yes\nx,yes\n'
        with self.assertRaises(ValueError):self.invoke(left,right,max_pairs=1)
        for field,value in [('join','inner'),('filter',{'op':'arbitrary','side':'right','column':'state','equals':'yes'}),
                            ('filter',{'op':'eq_or_unmatched','side':'left','column':'key','equals':'x'}),
                            ('filter',{'op':'eq_or_unmatched','side':'right','column':'state','equals':'yes','extra':True})]:
            plan=copy.deepcopy(PLAN);plan[field]=value
            with self.assertRaises(ValueError):self.invoke(left,right,plan)
        with self.assertRaises(ValueError):self.invoke('key,value\n,3\n',right)

    def test_randomized_sqlite_differential_120_cases(self):
        rng=random.Random(7514)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for i in range(120):
                left=[(rng.choice(['01','1','x','z']),rng.randrange(-10,11)) for _ in range(rng.randrange(9))]
                right=[(rng.choice(['01','1','x']),rng.choice(['yes','no',''])) for _ in range(rng.randrange(9))]
                literal=rng.choice(['yes','no',''])
                for name,header,rows in [('a.csv',['key','value'],left),('b.csv',['code','state'],right)]:
                    with (root/name).open('w',newline='') as f:
                        writer=csv.writer(f);writer.writerow(header);writer.writerows(rows)
                plan=copy.deepcopy(PLAN);plan['filter']['equals']=literal
                actual=execute_join_or_plan(plan,list(root.glob('*.csv')))
                with sqlite3.connect(':memory:') as db:
                    db.execute('CREATE TABLE a(key TEXT,value INTEGER)');db.execute('CREATE TABLE b(code TEXT,state TEXT)')
                    db.executemany('INSERT INTO a VALUES (?,?)',left);db.executemany('INSERT INTO b VALUES (?,?)',right)
                    expected=str(db.execute('SELECT COALESCE(SUM(a.value),0) FROM a LEFT JOIN b ON a.key=b.code WHERE b.state=? OR b.code IS NULL',(literal,)).fetchone()[0])
                self.assertEqual(actual,expected,(i,left,right,literal))

class JoinOrScopeControls(unittest.TestCase):
    def test_full_match_and_references(self):
        self.assertEqual(parse_join_or_scope(TEXT),PLAN)
        for text in (TEXT+' Exclude values over 5.',TEXT.replace('b.state','a.state'),TEXT.replace('Sum a.value','Sum b.value'),
                     TEXT.replace('OR there','AND there'),TEXT.replace('including duplicates','excluding duplicates'),
                     TEXT.replace('a.key','other.key'), 'Ignore this. '+TEXT):
            self.assertIsNone(parse_join_or_scope(text))
        self.assertEqual(parse_join_or_scope(TEXT.replace("'yes'","'OR no'"))['filter']['equals'],'OR no')

    def test_known_form_requires_consistent_absent_side(self):
        text="Using a.csv and b.csv, match every a.key with every b.code as exact strings. Keep only pairs where b.state is 'yes' OR there is no matching b row. Total a.value over all retained pairs, counting duplicate rows separately. Also include a without a matching label. Output only the numeric sum."
        self.assertEqual(parse_join_or_scope(text),PLAN)
        self.assertIsNone(parse_join_or_scope(text.replace('no matching b row','no matching a row')))
        self.assertIsNone(parse_join_or_scope(text.replace('Also include a','Also include b')))

class JoinOrRequestControls(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,text,cap):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'a.csv').write_text('key,value\nx,3\ny,4\n');(root/'b.csv').write_text('code,state\nx,yes\nx,yes\n')
            original={p.name:p.read_bytes() for p in root.iterdir()}
            ctx=TaskContext('or','data_analysis',text,2,root,root,cap,False)
            config=HarnessConfig(root,None,'https://fixture.invalid/v1','offline',initial_budget_tokens=cap)
            tracker=BudgetTracker(cap,max_requests=1);requests=[]
            async def send(payload):
                requests.append(payload)
                return dict(usage=dict(prompt_tokens=50,completion_tokens=10),choices=[dict(message=dict(content='print(123)'),finish_reason='stop')])
            with patch('harness.agents.base_harness.solve_data_task',solve_join_or_task):
                result=await solve_task(ctx,config,tracker,transport=send)
            self.assertEqual(original,{p.name:p.read_bytes() for p in root.iterdir()})
            return result,tracker,requests

    async def test_local_zero_budget_and_usage(self):
        result,tracker,requests=await self.invoke(TEXT,0)
        self.assertEqual((result.status,result.answer),('SOLVED','10'))
        self.assertEqual(requests,[]);self.assertEqual(tracker.events,[])
        self.assertEqual(result.model_used,'');self.assertEqual(result.effective_cost,0)

    async def test_extra_condition_uses_python_response(self):
        result,tracker,requests=await self.invoke(TEXT+' Exclude values above 7.',800)
        self.assertEqual((result.status,result.answer),('SOLVED','123'))
        self.assertEqual(len(requests),1);self.assertEqual(result.effective_cost,15)
        self.assertIn('Python',requests[0]['messages'][0]['content'])
