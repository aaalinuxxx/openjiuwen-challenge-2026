from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from plan_api_benchmark import paired_summary


class ComparisonTests(unittest.TestCase):
    def test_invalid_plan_still_counts_as_a_paired_failure(self):
        rows = [dict(task_id='a', arm='json', response='not json', correct=False,
                     status='INTERPRETATION_FAILED', effective_cost=12),
                dict(task_id='a', arm='python', response='print(3)', correct=True,
                     status='SOLVED', effective_cost=15),
                dict(task_id='b', arm='json', response='UNSUPPORTED', correct=False,
                     status='UNKNOWN', effective_cost=4),
                dict(task_id='b', arm='python', correct=False,
                     status='ERROR_OR_LOCAL_STOP', effective_cost=0)]
        result = paired_summary(rows)
        self.assertEqual(result['task_ids'], ['a'])
        self.assertEqual(result['arms']['json'], dict(attempted=1, correct=0, effective_tokens=12))
        self.assertEqual(result['arms']['python'], dict(attempted=1, correct=1, effective_tokens=15))


if __name__ == '__main__':
    unittest.main()
