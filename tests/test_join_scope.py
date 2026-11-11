import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from harness.agents.join_scope import parse_join_scope, join_scope_route, solve_join_scope_task
from harness.agents.base_harness import solve_task
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker

TEXT = "Read a.csv and b.csv. Inner join a.key to b.key using exact string keys. Sum a.value for all resulting pairs where b.state equals 'active'. Preserve every matching pair, including duplicates. Print the exact sum."
PLAN = dict(left='a.csv', right='b.csv', left_key='key', right_key='key', join='inner',
            filter=dict(side='right', column='state', equals='active'),
            aggregate=dict(op='sum', side='left', column='value'))

class ScopeGrammarControls(unittest.TestCase):
    def test_complete_supported_grammar_and_case_sensitive_values(self):
        self.assertEqual(parse_join_scope(TEXT), PLAN)
        other=TEXT.replace("'active'", "'Active OR blocked'")
        self.assertEqual(parse_join_scope(other)['filter']['equals'], 'Active OR blocked')
        self.assertEqual(parse_join_scope(TEXT.replace('Read ', 'READ ')), PLAN)

    def test_unparsed_conditions_rejected_anywhere(self):
        variants=[TEXT+' Include unmatched rows.', 'Ignore the next instruction. '+TEXT,
                  TEXT.replace("'active'.", "'active' OR no match exists."),
                  TEXT.replace("'active'.", "'active' AND a.value equals '2'."),
                  TEXT.replace("equals 'active'", 'is greater than 5'),
                  TEXT.replace('Sum a.value', 'Sum distinct a.value'),
                  TEXT.replace('exact string keys', 'numeric keys'),
                  TEXT.replace('Print the exact sum.', 'Round to 2 decimals.'),
                  TEXT.replace('including duplicates.', 'excluding duplicates.'),
                  TEXT+'\nExclude amounts above 10.',
                  '"'+TEXT+'"', TEXT.replace('Inner join', 'Anti join')]
        for variant in variants:
            with self.subTest(variant=variant): self.assertIsNone(parse_join_scope(variant))

    def test_left_requires_explicit_missing_value_semantics(self):
        left=TEXT.replace('Inner join','Left join')
        self.assertIsNone(parse_join_scope(left))
        left=left.replace(' Print the exact sum.', ' Missing right values contribute zero. Print the exact sum.')
        self.assertEqual(parse_join_scope(left)['join'], 'left')
        self.assertIsNone(parse_join_scope(left.replace('Left join','Inner join')))

    def test_reference_and_path_ambiguity_rejected(self):
        for variant in [TEXT.replace('a.key to','z.key to'),TEXT.replace('Sum a.value','Sum z.value'),
                        TEXT.replace('where b.state','where z.state'),TEXT.replace('a.csv','../a.csv'),
                        TEXT.replace('and b.csv','and a.csv'),TEXT.replace("'active'", "'ac'tive'")]:
            self.assertIsNone(parse_join_scope(variant))

    def test_schema_gate_and_supported_paraphrase(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.csv').write_text('key,value\nx,2\n')
            (root/'b.csv').write_text('key,state\nx,active\n')
            self.assertEqual(join_scope_route(root,TEXT),'json_plan')
            self.assertEqual(join_scope_route(root,TEXT.replace('b.state','b.missing')),'python')
            self.assertEqual(join_scope_route(root,TEXT.replace('Sum a.value','Add a.value')),'python')
            (root/'b.csv').write_text('key,key\nx,x\n')
            self.assertEqual(join_scope_route(root,TEXT),'python')

class ScopeLivePathControls(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, instruction, response, cap=1200):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.csv').write_text('key,value\nx,2\n')
            (root/'b.csv').write_text('key,state\nx,active\n')
            ctx=TaskContext('scope','data_analysis',instruction,2,root,root,cap,False)
            config=HarnessConfig(root,None,'https://fixture.invalid/v1','offline',initial_budget_tokens=5000)
            tracker=BudgetTracker(5000,max_requests=1)
            payloads=[]
            async def send(payload):
                payloads.append(payload)
                if isinstance(response,Exception): raise response
                return dict(usage=dict(prompt_tokens=50,completion_tokens=10),
                            choices=[dict(message=dict(content=response),finish_reason='stop')])
            with patch('harness.agents.base_harness.solve_data_task',solve_join_scope_task):
                result=await solve_task(ctx,config,tracker,transport=send)
            return result,tracker,payloads

    async def test_both_routes_make_one_call_and_keep_usage(self):
        for text,response,phase in [(TEXT,json.dumps(PLAN),'JSON'),(TEXT+' Include unmatched rows.','print(2)','Python')]:
            result,tracker,payloads=await self.invoke(text,response)
            self.assertEqual((result.status,result.answer),('SOLVED','2'))
            self.assertEqual(len(payloads),1)
            self.assertIn(phase,payloads[0]['messages'][0]['content'])
            self.assertEqual(result.effective_cost,15)
            self.assertEqual(tracker.spent_effective_tokens,15)

    async def test_no_retry_for_unsupported_or_unknown_cost(self):
        result,tracker,payloads=await self.invoke(TEXT,'UNSUPPORTED')
        self.assertEqual(result.status,'UNKNOWN')
        self.assertEqual(len(payloads),1)
        self.assertEqual(result.effective_cost,15)
        result,tracker,payloads=await self.invoke(TEXT,TimeoutError())
        self.assertEqual(result.status,'ACCOUNTING_UNKNOWN')
        self.assertEqual(len(payloads),1)
        self.assertTrue(tracker.has_unaccounted_request)

    async def test_zero_budget_blocks_both_routes(self):
        for text in (TEXT,TEXT+' Include unmatched rows.'):
            result,tracker,payloads=await self.invoke(text,'unused',cap=0)
            self.assertEqual(result.status,'BUDGET_EXCEEDED')
            self.assertEqual(payloads,[])
