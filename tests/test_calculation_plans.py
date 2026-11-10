from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.agents.calculation_plans import (SalesPlan,execute_sales_plan,
    parse_sales_plan,parse_warehouse_plan,execute_warehouse_plan,sales_plan_from_json)

class CalculationTests(unittest.TestCase):
    def test_json_plan_cannot_drop_unknown_filter(self):
        with self.assertRaises(ValueError):
            sales_plan_from_json('{"operation":"sum","product":"w","first_month":1,"last_month":2,"exclude_refunds":true}')

    def test_json_plan_types_duplicates_and_ranges(self):
        for text in (
            '{"operation":"sum","product":"w","first_month":true,"last_month":2}',
            '{"operation":"sum","product":"w","first_month":1,"first_month":2,"last_month":3}',
            '{"operation":"sum","product":"w","first_month":4,"last_month":2}',
            '{"operation":"sum","product":"w","first_month":1,"last_month":13}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                sales_plan_from_json(text)

    def test_json_unsupported_and_executable_plan(self):
        self.assertIsNone(sales_plan_from_json('UNSUPPORTED'))
        plan=sales_plan_from_json('{"operation":"sum","product":"w","first_month":1,"last_month":2}')
        self.assertEqual(self.csv('product,month,units\nw,1,3\nw,3,90\n',plan),('SOLVED','3'))

    def csv(self,body,plan):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sales.csv'; path.write_text(body,encoding='utf-8')
            return execute_sales_plan(path,plan)

    def test_revenue_decimal(self):
        body='product,month,units,price\nw,1,3,0.1\nw,2,2,0.2\n'
        self.assertEqual(self.csv(body,SalesPlan('revenue','w',1,2)),('SOLVED','0.7'))

    def test_large_exact_revenue(self):
        body='product,month,units,price\nw,1,123456789012345678901234567890,0.1\n'
        self.assertEqual(self.csv(body,SalesPlan('revenue','w',1,2)),('SOLVED','12345678901234567890123456789'))

    def test_empty_aggregate(self):
        body='product,month,units\n'
        self.assertEqual(self.csv(body,SalesPlan('sum','w',1,2)),('SOLVED','0'))
        self.assertEqual(self.csv(body,SalesPlan('mean','w',1,2)),('UNKNOWN',None))

    def test_no_implicit_rounding(self):
        body='product,month,units\nw,1,1\nw,1,0\nw,1,0\n'
        self.assertEqual(self.csv(body,SalesPlan('mean','w',1,2)),('UNKNOWN',None))

    def test_finite_numbers_and_duplicates(self):
        self.assertEqual(self.csv('product,month,units\nw,1,NaN\n',SalesPlan('sum','w',1,2)),('UNKNOWN',None))
        self.assertEqual(self.csv('product,month,units,units\nw,1,2,3\n',SalesPlan('sum','w',1,2)),('UNKNOWN',None))

    def test_missing_required_schema(self):
        self.assertEqual(self.csv('product,month\nw,1\n',SalesPlan('sum','w',1,2)),('UNSOLVABLE',None))

    def test_partial_operations_not_accepted(self):
        self.assertIsNone(parse_warehouse_plan('A warehouse starts with 100 boxes. It ships 2 boxes per day for 3 days and then loses 5 boxes. How many boxes does it have at the end?'))
        self.assertIsNone(parse_sales_plan("How many units of product 'w' were sold in months 1 through 2 inclusive excluding refunds?"))

    def test_order_of_operations(self):
        plan=parse_warehouse_plan('A warehouse starts with 17 boxes. It ships 2 boxes. Then the stock is split equally into 2 warehouses and it keeps one share (rounded down). It receives 3 boxes. How many boxes does it have at the end?')
        self.assertEqual(execute_warehouse_plan(plan),'10')

if __name__=='__main__': unittest.main()
