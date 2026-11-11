import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from harness.agents.base_harness import solve_task
from harness.config import HarnessConfig,TaskContext,SolveResult
from harness.planner.scheduler import TaskScheduler
from harness.planner.budget_tracker import BudgetTracker
from run_agent import parse_args
import json

TEXT="Read a.csv and b.csv. Left join a.key to b.code using exact string keys. Sum a.value for all resulting pairs where b.state equals 'yes' OR there is no matching right row. Preserve every matching pair, including duplicates. Print the exact sum."

class JoinIntegrationConfig(unittest.TestCase):
    def test_cli_opt_in_and_default(self):
        self.assertFalse(parse_args([]).experimental_joins)
        self.assertTrue(parse_args(['--experimental-joins']).experimental_joins)
    def test_rejects_non_boolean_config(self):
        with self.assertRaises(ValueError):HarnessConfig(Path('.'),None,'x','x',experimental_joins='false')

class JoinIntegrationRouting(unittest.IsolatedAsyncioTestCase):
    async def test_only_data_dispatch_changes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for enabled in (False,True):
                cfg=HarnessConfig(root,None,'https://fixture.invalid/v1','offline',experimental_joins=enabled)
                for kind in ('math','search','coding','data_analysis'):
                    ctx=TaskContext('id',kind,'instruction',1,root,root,0,False)
                    mocks={k:AsyncMock(return_value=SolveResult(task_id='id',status='UNKNOWN')) for k in ('math','search','coding','data')}
                    candidate=AsyncMock(return_value=SolveResult(task_id='id',status='UNKNOWN'))
                    with patch('harness.agents.base_harness.solve_math_task',mocks['math']),patch('harness.agents.base_harness.solve_search_task',mocks['search']),patch('harness.agents.base_harness.solve_coding_task',mocks['coding']),patch('harness.agents.base_harness.solve_data_task',mocks['data']),patch('harness.agents.join_or.solve_join_or_task',candidate):
                        await solve_task(ctx,cfg,BudgetTracker(0))
                    self.assertEqual(candidate.await_count,int(enabled and kind=='data_analysis'))
                    for name,mock in mocks.items():
                        expected=(kind==('data_analysis' if name=='data' else name)) and not(enabled and kind=='data_analysis')
                        self.assertEqual(mock.await_count,int(expected))

    async def test_real_scheduler_and_sdk_deliver_local_answer_at_zero_budget(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for enabled in (False,True):
                taskroot=root/str(enabled);task=taskroot/'join';task.mkdir(parents=True)
                (task/'task.json').write_text(json.dumps(dict(task_id='join',task_type='data_analysis',instruction=TEXT,reward=3)))
                (task/'a.csv').write_text('key,value\nx,3\ny,4\n')
                (task/'b.csv').write_text('code,state\nx,yes\nx,yes\n')
                cfg=HarnessConfig(taskroot,None,'https://fixture.invalid/v1','offline',initial_budget_tokens=0,max_api_calls=0,max_concurrency=1,experimental_joins=enabled)
                with patch('harness.agents.base_harness.OpenJiuwenLLMBridge._get_transport',side_effect=AssertionError('No HTTP allowed')):
                    summary=await TaskScheduler(cfg).run_all()
                result=summary['task_results']['join']
                self.assertEqual(summary['budget_state']['events'],[])
                self.assertEqual(result['status'],'SOLVED' if enabled else 'UNKNOWN')
                self.assertEqual((task/'answer.txt').exists(),enabled)
                if enabled:self.assertEqual((task/'answer.txt').read_text().strip(),'10')
                self.assertEqual(summary['workflow_runs'][0]['stages'],['solve','finalize'])
