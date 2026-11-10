from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from replay_plan_policies import replay
from harness.agents.plan_scope import json_plan_risks


class PlanScopeTests(unittest.TestCase):
    def test_constraints_beyond_filters(self):
        for question in ('Exclude refunded rows.', 'Use price at least 0.20.',
                         'Median units for widget.', 'Sum units in months 2 and 4.'):
            with self.subTest(question=question):
                self.assertTrue(json_plan_risks(question, ['product', 'region', 'month', 'units', 'price', 'refunded']))

    def test_metadata_column_does_not_alone_trigger_route(self):
        self.assertEqual(json_plan_risks('Count records, not units, for widget in months 2 and 3.',
                                        ['product', 'month', 'units', 'refunded']), [])

    def test_replay_never_uses_correctness_or_support_label_to_route(self):
        report = dict(mode='LIVE_PILOT', has_unaccounted_request=False, table='product,month,units,refunded\n',
                      cases=[dict(id='case', question='Sum widget units in months 2 and 3.', expected='3', json_supported=False)],
                      rows=[dict(task_id='case', arm='json', response='{}', status='SOLVED', answer='999', effective_cost=10, correct=False),
                            dict(task_id='case', arm='python', response='print(3)', status='SOLVED', answer='3', effective_cost=20, correct=True)])
        summary, rows = replay(report)
        self.assertEqual(summary['json_then_python_on_failure']['correct'], 0)
        self.assertEqual(summary['risk_gate_then_cascade']['correct'], 0)
        self.assertEqual(summary['risk_gate_then_cascade']['replay_effective_tokens'], 10)
        report['cases'][0]['question'] += ' Exclude refunded rows.'
        summary, rows = replay(report)
        self.assertEqual(summary['risk_gate_then_cascade']['correct'], 1)
        self.assertEqual(summary['risk_gate_then_cascade']['replay_effective_tokens'], 20)

    def test_failed_json_cost_is_kept_in_cascade(self):
        report = dict(mode='LIVE_PILOT', has_unaccounted_request=False, table='product,month,units\n',
                      cases=[dict(id='case', question='Sum widget units.', expected='3')],
                      rows=[dict(task_id='case', arm='json', response='UNSUPPORTED', status='UNKNOWN', answer=None, effective_cost=10),
                            dict(task_id='case', arm='python', response='print(3)', status='SOLVED', answer='3', effective_cost=20)])
        summary, rows = replay(report)
        self.assertEqual(summary['json_then_python_on_failure']['correct'], 1)
        self.assertEqual(summary['json_then_python_on_failure']['replay_effective_tokens'], 30)
        self.assertEqual(summary['json_then_python_on_failure']['replay_calls'], 2)


if __name__ == '__main__':
    unittest.main()
