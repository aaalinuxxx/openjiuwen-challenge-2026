import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from harness.agents.join_scope import parse_join_scope
from harness.agents.join_scope_v2 import parse_join_scope_v2, join_scope_v2_route, solve_join_scope_v2_task
from harness.agents.join_plans import execute_join_plan
from harness.agents.base_harness import solve_task
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker

A = "From a.csv and b.csv, keep every pair with identical key strings and a.state equal to 'open'. Add b.value across those pairs. Duplicate rows must contribute repeatedly. Return the sum as a number."
B = "Using a.csv and b.csv, match every a.key with every b.code as exact strings. Keep only pairs where a.state is 'open'. Total b.value over all retained pairs, counting duplicate rows separately. Output only the numeric sum."

class ScopeV2GrammarControls(unittest.TestCase):
    def test_two_patterns_capture_sides_keys_and_literals(self):
        for text,rk in ((A,'key'),(B,'code')):
            plan=parse_join_scope_v2(text)
            self.assertEqual(plan['right_key'],rk)
            self.assertEqual(plan['filter'],dict(side='left',column='state',equals='open'))
            self.assertEqual(plan['aggregate'],dict(op='sum',side='right',column='value'))
            literal=text.replace("'open'","'Open OR closed'")
            self.assertEqual(parse_join_scope_v2(literal)['filter']['equals'],'Open OR closed')

    def test_rejects_unparsed_clauses_and_changed_semantics(self):
        for text in (A,B):
            for variant in (text+' Except rows with value 9.', 'Ignore this: '+text,
                            text.replace("'open'.","'open' OR no match exists."),
                            text.replace("'open'.","'open' AND b.value exceeds 3."),
                            text.replace('strings','numbers'),
                            text.replace('Duplicate rows must contribute repeatedly','Ignore duplicate rows'),
                            text.replace('counting duplicate rows separately','counting only unique rows'),
                            text.replace('as a number','rounded to an integer'),
                            text.replace('numeric sum','average')):
                if variant==text: continue
                with self.subTest(text=variant): self.assertIsNone(parse_join_scope_v2(variant))

    def test_rejects_unknown_references_and_quoting(self):
        for text in (A,B):
            for variant in (text.replace('a.csv','../a.csv'),text.replace('b.csv','a.csv'),
                            text.replace('a.state','x.state'),text.replace('b.value','x.value'),
                            text.replace("'open'","'op'en'"),'"'+text+'"'):
                self.assertIsNone(parse_join_scope_v2(variant))
        self.assertIsNone(parse_join_scope_v2(B.replace('a.key','b.key')))
        self.assertIsNone(parse_join_scope_v2(B.replace('b.code','x.code')))

    def test_preserves_previous_grammar(self):
        text='Read a.csv and b.csv. Left join a.key to b.code using exact string keys. Sum b.value for all resulting pairs. Preserve every matching pair, including duplicates. Missing right values contribute zero. Print the exact sum.'
        self.assertEqual(parse_join_scope_v2(text),parse_join_scope(text))
        self.assertIsNone(parse_join_scope_v2(text+' Exclude missing matches.'))

    def test_duplicate_multiplicity_and_schema_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.csv').write_text('key,state\n01,open\n1,closed\n01,open\n')
            (root/'b.csv').write_text('code,value\n01,3\n1,100\n01,4\n')
            self.assertEqual(join_scope_v2_route(root,B),'json_plan')
            self.assertEqual(execute_join_plan(parse_join_scope_v2(B),list(root.glob('*.csv'))),'14')
            self.assertEqual(join_scope_v2_route(root,A),'python')  # b.key is absent
            self.assertEqual(join_scope_v2_route(root,B.replace('b.value','b.absent')),'python')
            (root/'b.csv').write_text('code,code\n01,01\n')
            self.assertEqual(join_scope_v2_route(root,B),'python')

class ScopeV2RequestControls(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,text,response):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.csv').write_text('key,state\nx,open\n')
            (root/'b.csv').write_text('code,value\nx,7\n')
            ctx=TaskContext('scopev2','data_analysis',text,2,root,root,1200,False)
            config=HarnessConfig(root,None,'https://fixture.invalid/v1','offline',initial_budget_tokens=5000)
            tracker=BudgetTracker(5000,max_requests=1)
            payloads=[]
            async def send(payload):
                payloads.append(payload)
                return dict(usage=dict(prompt_tokens=50,completion_tokens=10),
                            choices=[dict(message=dict(content=response),finish_reason='stop')])
            with patch('harness.agents.base_harness.solve_data_task',solve_join_scope_v2_task):
                result=await solve_task(ctx,config,tracker,transport=send)
            return result,tracker,payloads

    async def test_both_routes_use_actual_response_and_account_usage(self):
        for text,response,phase in ((B,json.dumps(parse_join_scope_v2(B)),'JSON'),
                                    (B+' Exclude values above 20.','print(7)','Python')):
            result,tracker,payloads=await self.invoke(text,response)
            self.assertEqual((result.status,result.answer),('SOLVED','7'))
            self.assertEqual(len(payloads),1)
            self.assertIn(phase,payloads[0]['messages'][0]['content'])
            self.assertEqual(result.effective_cost,15)
            self.assertEqual(tracker.spent_effective_tokens,15)

    async def test_no_gold_substitution_or_retry_on_model_refusal(self):
        result,tracker,payloads=await self.invoke(B,'UNSUPPORTED')
        self.assertEqual(result.status,'UNKNOWN')
        self.assertIsNone(result.answer)
        self.assertEqual(len(payloads),1)
        self.assertEqual(result.effective_cost,15)
