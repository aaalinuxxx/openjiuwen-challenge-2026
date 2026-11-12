import json, shutil, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from harness.config import HarnessConfig,TaskContext
from harness.agents.base_harness import solve_task
from harness.planner.budget_tracker import BudgetTracker
ROOT=Path(__file__).resolve().parents[1]
RECORD=ROOT/'experiments/E86_mixed_profile_live_20261112T184718872839/response_11.json'
MODEL='qwen3.6-35b-a3b-noreason'

class AttemptedModelTests(unittest.IsolatedAsyncioTestCase):
    async def run_record(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=ROOT/'experiments/E77_mixed_integration/tasks/pilot_extra_numeric_control'
            shutil.copytree(src,root,dirs_exist_ok=True)
            meta=json.loads((root/'task.json').read_text())
            ctx=TaskContext(meta['task_id'],'data_analysis',meta['instruction'],3,root,root,700,False)
            cfg=HarnessConfig(root,None,'https://fixture.invalid/v1','offline',initial_budget_tokens=3000,experimental_joins=True)
            tracker=BudgetTracker(0 if mode=='denied' else 3000)
            payloads=[]
            async def transport(payload):
                payloads.append(payload)
                if mode=='network':raise TimeoutError('fixture timeout; no actual HTTP')
                data=json.loads(RECORD.read_text())['response']
                if mode=='malformed':data['choices']=[]
                return data
            result=await solve_task(ctx,cfg,tracker,transport=transport)
            return result,tracker,payloads

    async def test_recorded_real_truncation_preserves_actual_model_and_usage(self):
        result,tracker,payloads=await self.run_record('truncated')
        self.assertEqual((result.status,result.model_used),('TRUNCATED',MODEL))
        self.assertEqual(result.effective_cost,431.5)
        self.assertEqual(payloads[0]['model'],MODEL)
        self.assertFalse(tracker.snapshot()['has_unaccounted_request'])

    async def test_known_usage_malformed_response_keeps_model(self):
        result,tracker,payloads=await self.run_record('malformed')
        self.assertEqual((result.status,result.model_used),('FAILED',MODEL))
        self.assertEqual(result.effective_cost,431.5)
        self.assertFalse(tracker.snapshot()['has_unaccounted_request'])

    async def test_unknown_request_keeps_attempted_model(self):
        result,tracker,payloads=await self.run_record('network')
        self.assertEqual((result.status,result.model_used),('ACCOUNTING_UNKNOWN',MODEL))
        self.assertTrue(tracker.snapshot()['has_unaccounted_request'])

    async def test_no_request_has_no_model(self):
        result,tracker,payloads=await self.run_record('denied')
        self.assertEqual((result.status,result.model_used),('BUDGET_EXCEEDED',''))
        self.assertEqual(payloads,[])

    async def test_local_solution_has_no_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=ROOT/'experiments/E77_mixed_integration/tasks/pilot_known_or_failure'
            shutil.copytree(src,root,dirs_exist_ok=True);meta=json.loads((root/'task.json').read_text())
            ctx=TaskContext(meta['task_id'],'data_analysis',meta['instruction'],3,root,root,0,False)
            cfg=HarnessConfig(root,None,'x','offline',initial_budget_tokens=0,experimental_joins=True)
            with patch('harness.agents.base_harness.OpenJiuwenLLMBridge._get_transport',side_effect=AssertionError('No HTTP')):
                result=await solve_task(ctx,cfg,BudgetTracker(0))
            self.assertEqual((result.status,result.answer,result.model_used),('SOLVED','30',''))
