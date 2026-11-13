import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from numeric_recheck_policy import numeric_literal_only,calculate_again,CALCULATION_PROMPT
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker
from harness.agents.base_harness import OpenJiuwenLLMBridge
class NumericSignalTests(unittest.TestCase):
    def test_literals_and_aliases(self):
        for code in ('print(17395)','4','print(-42)','print("31")','x=31\ny=x\nprint(y)','\x60\x60\x60python\nprint(2)\n\x60\x60\x60'):
            self.assertTrue(numeric_literal_only(code),code)
    def test_computations_and_refusals_not_signalled(self):
        for code in ('print(1+2)','print(sum(range(10)))','print("UNSOLVABLE")','print(True)','print(float("inf"))','print(', 'x=2\nx+=3\nprint(x)'):
            self.assertFalse(numeric_literal_only(code),code)
    def test_ast_is_not_a_correctness_proof(self):
        self.assertFalse(numeric_literal_only('print(17395+0)'))
        self.assertTrue(numeric_literal_only('print(17575)'))
class CorrectionTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,content,finish='stop',failure=False,budget=500):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=HarnessConfig(root,None,'','',execution_engine='direct',initial_budget_tokens=budget)
            ctx=TaskContext('a','math','Sum squares of1..37.',3,root,root,500,False)
            tracker=BudgetTracker(budget);sent=[]
            def transport(owner):
                async def send(payload):
                    sent.append(payload)
                    if failure:raise TimeoutError()
                    return {'choices':[{'finish_reason':finish,'message':{'content':content}}],'usage':{'prompt_tokens':10,'completion_tokens':20}}
                return send
            with patch.object(OpenJiuwenLLMBridge,'_get_transport',transport):result=await calculate_again(ctx,cfg,tracker)
            return result,tracker,sent
    async def test_real_computation_and_full_usage(self):
        result,tracker,sent=await self.exercise('print(sum(k*k for k in range(1,38)))')
        self.assertEqual((result.status,result.answer),('SOLVED','17575'))
        self.assertEqual(tracker.spent_effective_tokens,21)
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['messages'][0]['content'],CALCULATION_PROMPT)
        self.assertEqual(sent[0]['messages'][1]['content'],'Sum squares of1..37.')
    async def test_literal_not_accepted_even_when_numerically_correct(self):
        result,tracker,sent=await self.exercise('print(17575)')
        self.assertEqual(result.status,'UNKNOWN');self.assertIsNone(result.answer)
        self.assertEqual(len(sent),1);self.assertEqual(tracker.spent_effective_tokens,21)
    async def test_truncation_settled_without_retry(self):
        result,tracker,sent=await self.exercise('print(',finish='length')
        self.assertEqual(result.status,'TRUNCATED');self.assertEqual(len(sent),1)
        self.assertFalse(tracker.has_unaccounted_request)
    async def test_unknown_cost_stops_and_retains_reservation(self):
        result,tracker,sent=await self.exercise('',failure=True)
        self.assertEqual(result.status,'ACCOUNTING_UNKNOWN');self.assertEqual(len(sent),1)
        self.assertTrue(tracker.has_unaccounted_request);self.assertGreater(tracker.reserved_effective_tokens,0)
    async def test_zero_budget_makes_no_request(self):
        result,tracker,sent=await self.exercise('',budget=0)
        self.assertEqual(result.status,'BUDGET_EXCEEDED');self.assertFalse(sent)
if __name__=='__main__':unittest.main()
