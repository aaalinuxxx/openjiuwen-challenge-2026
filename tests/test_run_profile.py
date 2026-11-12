import unittest
from unittest.mock import patch
from run_agent import parse_args, build_config

class RunProfileTests(unittest.TestCase):
    def config(self, flags):
        with patch.dict('os.environ', {}, clear=True):
            return build_config(parse_args(['--tasks-dir', '.', '--budget', '3000']+flags), settings={})

    def test_default_preserves_previous_behavior(self):
        c=self.config([])
        self.assertEqual((c.experimental_joins,c.search_min_task_budget,c.data_min_task_budget,c.max_concurrency),(False,0,0,5))

    def test_validated_matches_live_settings(self):
        c=self.config(['--profile','validated','--max-api-calls','26'])
        self.assertEqual((c.experimental_joins,c.search_min_task_budget,c.data_min_task_budget,c.coding_min_task_budget,c.max_concurrency),(True,300,700,800,1))
        self.assertEqual((c.initial_budget_tokens,c.max_api_calls),(3000,26))

    def test_explicit_limits_override_profile(self):
        c=self.config(['--profile','validated','--max-concurrency','2','--max-api-calls','0'])
        self.assertEqual((c.max_concurrency,c.max_api_calls),(2,0))
