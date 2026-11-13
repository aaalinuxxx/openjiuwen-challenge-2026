import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from score_selection_benchmark import candidate_completion,BASELINE_MATH_PROMPT,TERSE_MATH_PROMPT,CALCULATION_PROMPT
from harness.agents.base_harness import OpenJiuwenLLMBridge
from harness.config import HarnessConfig,TaskContext
from harness.planner.budget_tracker import BudgetTracker
class SelectionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,arm='terse_recheck',first='print(9)',second='print(5+5)',finish='stop',limit=None,fail=False,prompt=BASELINE_MATH_PROMPT):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=HarnessConfig(root,None,'','',execution_engine='direct',initial_budget_tokens=1000)
            ctx=TaskContext('test','math','Add five and five.',3,root,root,1000,False);tracker=BudgetTracker(1000,max_requests=limit);sent=[]
            async def transport(payload):
                sent.append(payload)
                if len(sent)==2 and fail:raise TimeoutError()
                return dict(choices=[dict(finish_reason=finish if len(sent)==2 else 'stop',message=dict(content=first if len(sent)==1 else second))],usage=dict(prompt_tokens=10,completion_tokens=20))
            bridge=OpenJiuwenLLMBridge(cfg,tracker,ctx,transport)
            try:result=await candidate_completion(OpenJiuwenLLMBridge.complete,arm)(bridge,'qwen3.6-27b-noreason',prompt,ctx.instruction,max_tokens=200)
            except Exception as exc:result=exc
            return result,tracker,sent
    async def test_corrective_call_uses_same_budget_and_input(self):
        result,tracker,sent=await self.exercise()
        self.assertEqual(result[0],'print(5+5)');self.assertEqual(tracker.spent_effective_tokens,42)
        self.assertEqual(tracker.usage_for_task('test'),(20,40,0));self.assertEqual(len(sent),2)
        self.assertEqual(sent[0]['messages'][0]['content'],TERSE_MATH_PROMPT)
        self.assertEqual(sent[1]['messages'][0]['content'],CALCULATION_PROMPT)
        self.assertEqual(sent[0]['messages'][1],sent[1]['messages'][1])
    async def test_denied_correction_keeps_original_without_call(self):
        result,tracker,sent=await self.exercise(limit=1)
        self.assertEqual(result[0],'print(9)');self.assertEqual(len(sent),1)
    async def test_truncation_is_paid_and_does_not_retry(self):
        result,tracker,sent=await self.exercise(finish='length')
        self.assertEqual(result[0],'print(9)');self.assertEqual(len(sent),2)
        self.assertEqual(tracker.spent_effective_tokens,42);self.assertFalse(tracker.has_unaccounted_request)
    async def test_unknown_cost_propagates_and_reserves(self):
        result,tracker,sent=await self.exercise(fail=True)
        self.assertIsInstance(result,TimeoutError);self.assertTrue(tracker.has_unaccounted_request)
        self.assertGreater(tracker.reserved_effective_tokens,0);self.assertEqual(len(sent),2)
    async def test_computation_and_nonmath_need_no_correction(self):
        for kwargs in (dict(first='print(5+5)'),dict(prompt='Solve a CSV task'),dict(arm='terse'),dict(arm='baseline')):
            result,tracker,sent=await self.exercise(**kwargs);self.assertEqual(len(sent),1)
    async def test_second_constant_is_not_evidence(self):
        result,tracker,sent=await self.exercise(second='print(10)')
        self.assertEqual(result[0],'print(9)');self.assertEqual(len(sent),2)
if __name__=='__main__':unittest.main()
