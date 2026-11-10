import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.agents.extended_plans import extended_plan_from_json, execute_extended_plan


class ExtendedPlanTests(unittest.TestCase):
    def execute(self, table, **changes):
        obj = dict(operation='sum', product='w', months=[2,3])
        obj.update(changes)
        plan = extended_plan_from_json(json.dumps(obj))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.csv'
            path.write_text(table, encoding='utf-8')
            return execute_extended_plan(path, plan)

    def test_noncontiguous_months_do_not_fill_gap(self):
        self.assertEqual(self.execute('product,month,units\nw,2,4\nw,3,100\nw,4,30\n', months=[2,4]), ('SOLVED','34'))

    def test_conjunction_and_numeric_boundary(self):
        table='product,month,units,price,refunded\nw,2,4,0.200,no\nw,2,100,0.19,no\nw,3,200,0.4,yes\n'
        filters=[dict(column='price',op='ge',value='0.20'),dict(column='refunded',op='ne',value='yes')]
        self.assertEqual(self.execute(table,predicates=filters),('SOLVED','4'))

    def test_even_median_is_exact_and_order_independent(self):
        self.assertEqual(self.execute('product,month,units\nw,2,99\nw,2,1\nw,2,3\nw,2,2\n',operation='median'),('SOLVED','2.5'))

    def test_nonterminating_mean_and_empty_median(self):
        self.assertEqual(self.execute('product,month,units\nw,2,1\nw,2,0\nw,2,0\n',operation='mean'),('UNKNOWN',None))
        self.assertEqual(self.execute('product,month,units\n',operation='median'),('UNKNOWN',None))

    def test_hallucinated_column_is_not_proof_of_unsolvability(self):
        self.assertEqual(self.execute('product,month,units\nw,2,4\n',predicates=[dict(column='invented',op='eq',value='no')]),('UNKNOWN',None))

    def test_invalid_numbers_and_short_rows(self):
        for table in ('product,month,units\nw,2,NaN\n', 'product,month,units\nw,2\n',
                      'product,month,units\nw,2,1e1000000\n'):
            with self.subTest(table=table): self.assertEqual(self.execute(table),('UNKNOWN',None))

    def test_bad_schema_and_duplicate_nested_fields(self):
        base=dict(operation='sum',product='w',months=[2,3])
        for changes in (dict(months=[True,3]),dict(months=[2,2]),dict(months=[0,2]),
                        dict(predicates=[dict(column='price',op='ge',value='NaN')]),
                        dict(predicates=[dict(column='refunded',op='eq',value=False)]),
                        dict(where='refunded=no')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                extended_plan_from_json(json.dumps({**base,**changes}))
        with self.assertRaises(ValueError):
            extended_plan_from_json('{"operation":"sum","product":"w","months":[2],"predicates":[{"column":"price","op":"gt","op":"lt","value":"1"}]}')


if __name__ == '__main__': unittest.main()
