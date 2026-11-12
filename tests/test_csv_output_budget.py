import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from run_agent import parse_args,build_config
from harness.config import TaskContext,HarnessConfig
from harness.agents.base_harness import solve_task
from harness.planner.budget_tracker import BudgetTracker
ROOT=Path(__file__).resolve().parents[1]

class CSVOutputBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def check_payload(self,budget):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            shutil.copytree(ROOT/'experiments/E87_numeric_joins/holdout/tasks/hold_postfilter',root,dirs_exist_ok=True)
            public=json.loads((root/'task.json').read_text())
            with patch.dict('os.environ',{},clear=True):
                cfg=build_config(parse_args(['--tasks-dir',str(root),'--profile','csv-roomy','--budget',str(budget)]),settings={})
            ctx=TaskContext(public['task_id'],'data_analysis',public['instruction'],3,root,root,cfg.data_min_task_budget,False)
            payloads=[]
            async def send(payload):
                payloads.append(payload)
                return dict(usage=dict(prompt_tokens=50,completion_tokens=5),choices=[dict(finish_reason='stop',message=dict(content='print(4)'))])
            tracker=BudgetTracker(budget)
            result=await solve_task(ctx,cfg,tracker,transport=send)
            self.assertEqual((result.status,result.answer),('SOLVED','4'))
            self.assertEqual(result.effective_cost,10)
            self.assertFalse(tracker.snapshot()['has_unaccounted_request'])
            return payloads[0],tracker

    async def test_roomy_profile_actually_sends_600(self):
        payload,tracker=await self.check_payload(3000)
        self.assertEqual(payload['max_tokens'],600)

    async def test_small_global_budget_still_limits_output(self):
        payload,tracker=await self.check_payload(500)
        self.assertGreater(payload['max_tokens'],0)
        self.assertLess(payload['max_tokens'],600)
        self.assertLessEqual(tracker.events[0]['reserved_units'],5000)

    def test_invalid_caps_rejected(self):
        for cap in (True,0,-1,1.5,5000):
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                HarnessConfig(Path('.'),None,'x','x',multi_csv_max_output_tokens=cap)
