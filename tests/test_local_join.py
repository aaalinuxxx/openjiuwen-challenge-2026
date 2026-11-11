from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from harness.agents.local_join import solve_local_join_task
from harness.agents.base_harness import solve_task
from harness.config import HarnessConfig, TaskContext
from harness.planner.budget_tracker import BudgetTracker

TEXT = "From a.csv and b.csv, keep every pair with identical key strings and a.state equal to 'open'. Add b.value across those pairs. Duplicate rows must contribute repeatedly. Return the sum as a number."

class LocalJoinControls(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, text=TEXT, left='key,state\n01,open\n1,closed\n01,open\n',
                     right='key,value\n01,0.10\n1,99\n01,0.20\n', cap=800, total=4000, uncertain=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.csv').write_text(left)
            (root/'b.csv').write_text(right)
            original={p.name:p.read_bytes() for p in root.iterdir()}
            ctx=TaskContext('localjoin','data_analysis',text,2,root,root,cap,False)
            config=HarnessConfig(root,None,'https://fixture.invalid/v1','offline',initial_budget_tokens=total)
            tracker=BudgetTracker(total,max_requests=2)
            if uncertain:
                ticket,_=await tracker.reserve('other',1000,100,100)
                await tracker.unknown(ticket,'SyntheticPriorTimeout')
            requests=[]
            async def send(payload):
                requests.append(payload)
                return dict(usage=dict(prompt_tokens=50,completion_tokens=10),
                            choices=[dict(message=dict(content='print(123)'),finish_reason='stop')])
            with patch('harness.agents.base_harness.solve_data_task',solve_local_join_task):
                result=await solve_task(ctx,config,tracker,transport=send)
            self.assertEqual(original,{p.name:p.read_bytes() for p in root.iterdir()})
            return result,tracker,requests

    async def test_local_exact_decimal_duplicate_sum_never_calls_transport(self):
        result,tracker,requests=await self.invoke()
        self.assertEqual((result.status,result.answer),('SOLVED','0.6'))
        self.assertEqual(requests,[])
        self.assertEqual(tracker.events,[])
        self.assertEqual(result.effective_cost,0)
        self.assertFalse(result.model_used)

    async def test_empty_join_is_zero_without_api(self):
        result,tracker,requests=await self.invoke(right='key,value\nx,3\n')
        self.assertEqual((result.status,result.answer),('SOLVED','0'))
        self.assertEqual(requests,[])

    async def test_local_runs_with_zero_global_and_task_budget(self):
        result,tracker,requests=await self.invoke(cap=0,total=0)
        self.assertEqual((result.status,result.answer),('SOLVED','0.6'))
        self.assertEqual(requests,[])
        self.assertEqual(tracker.events,[])

    async def test_local_does_not_clear_prior_unknown_cost(self):
        result,tracker,requests=await self.invoke(uncertain=True)
        self.assertEqual((result.status,result.answer),('SOLVED','0.6'))
        self.assertEqual(requests,[])
        self.assertTrue(tracker.has_unaccounted_request)
        self.assertEqual(len(tracker.events),1)
        self.assertGreater(tracker.reserved_effective_tokens,0)

    async def test_invalid_local_data_declines_without_paid_retry(self):
        for right in ('key,value\n01,NaN\n','key,value\n01,oops\n','key,value\n,5\n'):
            result,tracker,requests=await self.invoke(right=right)
            self.assertEqual(result.status,'UNKNOWN')
            self.assertIsNone(result.answer)
            self.assertEqual(requests,[])
            self.assertEqual(result.effective_cost,0)

    async def test_extra_condition_goes_to_actual_python_response(self):
        result,tracker,requests=await self.invoke(text=TEXT+' Exclude values above 7.')
        self.assertEqual((result.status,result.answer),('SOLVED','123'))
        self.assertEqual(len(requests),1)
        self.assertIn('Python',requests[0]['messages'][0]['content'])
        self.assertEqual(result.effective_cost,15)

    async def test_outside_grammar_is_not_solved_for_free_at_zero_budget(self):
        result,tracker,requests=await self.invoke(text=TEXT+' Exclude values above 7.',cap=0,total=0)
        self.assertEqual(result.status,'BUDGET_EXCEEDED')
        self.assertEqual(requests,[])
