"""Production calibration must change order only, never allocation estimates."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from run_agent import parse_args,build_config
from harness.config import HarnessConfig
from harness.planner.scheduler import TaskScheduler
from harness.planner.ranking_calibration import MEDIAN_ORDERING_COSTS
class ProductionRankingTests(unittest.TestCase):
    def config(self,flags):
        with patch.dict('os.environ',{},clear=True):return build_config(parse_args(['--tasks-dir','.','--budget','3000']+flags),settings={})
    def test_default_matches_explicit_calibration(self):
        self.assertEqual(self.config([]),self.config(['--ranking-policy','calibrated']))
        self.assertEqual(self.config([]).ranking_policy,'calibrated')
    def test_rollback_and_legacy_are_available(self):
        self.assertEqual(self.config(['--ranking-policy','roi']).ranking_policy,'roi')
        self.assertEqual(self.config(['--profile','legacy']).ranking_policy,'roi')
    def test_order_changes_but_expected_cost_and_budget_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,kind,reward in [('a_math','math',2),('b_search','search',3),('c_other','other',1)]:
                folder=root/name;folder.mkdir();(folder/'task.json').write_text(json.dumps(dict(task_id=name,task_type=kind,instruction='Compute the requested value.',reward=reward)),encoding='utf-8')
                if kind=='search':
                    (folder/'kb').mkdir();(folder/'kb/card.md').write_text('# Entry\nvalue: 1\n',encoding='utf-8')
            class Estimator:
                def estimate(self,features):return .9,{'math':10,'search':1000,'other':500}[features.task_type]
            orders={};costs={};allocations={}
            for policy in ('roi','calibrated'):
                config=HarnessConfig(root,None,'https://fixture.invalid','',execution_engine='direct',ranking_policy=policy)
                sched=TaskScheduler(config);sched.estimator=Estimator();rows=sched.discover_and_rank_tasks()
                orders[policy]=[r['task_id'] for r in rows];costs[policy]={r['task_id']:r['expected_cost'] for r in rows}
                allocations[policy]={r['task_id']:sched.budget_tracker.allocate_task_budget(r['expected_cost'],r['reward']) for r in rows}
            self.assertEqual(orders['roi'],['a_math','b_search','c_other'])
            self.assertEqual(orders['calibrated'],['b_search','a_math','c_other'])
            self.assertEqual(costs['roi'],costs['calibrated']);self.assertEqual(allocations['roi'],allocations['calibrated'])
    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):HarnessConfig(Path('.'),None,'https://fixture.invalid','',ranking_policy='reward')
    def test_frozen_costs_are_not_mutable(self):
        with self.assertRaises(TypeError):MEDIAN_ORDERING_COSTS['math']=1
if __name__=='__main__':unittest.main()
