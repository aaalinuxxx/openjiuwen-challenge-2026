"""E22 dev follow-up, frozen before model calls. Same DSL and prompts as E19.

Two representable controls and four expressivity limits. Reference arithmetic
is independent from the plan executor; fixtures validate mechanics only.
"""
import json

TABLE = ('product,region,month,units,price,refunded\n'
         'widget,north,2,4,0.25,no\nwidget,south,3,16,0.10,yes\n'
         'gadget,north,1,100,0.15,no\nwidget,north,3,8,0.50,no\n'
         'widget,north,4,30,0.40,no\n')


def cases():
    definitions = [
        ('total_control', 'Give total units for widget over months 2 and 3, combining all regions.',
         'sum', '28', "r['month'] in ('2','3')", 'sum(values)', True),
        ('count_control', 'How many widget records are dated February or March, across all regions? Count rows, not units.',
         'count', '3', "r['month'] in ('2','3')", 'len(values)', True),
        ('refund_alias', 'Total the units for widget rows in months 2 and 3 whose refunded value is no.',
         'sum', '12', "r['month'] in ('2','3') and r['refunded']=='no'", 'sum(values)', False),
        ('price_threshold', 'Sum units for widget in months 2 and 3, keeping only rows with price at least 0.20.',
         'sum', '12', "r['month'] in ('2','3') and Decimal(r['price'])>=Decimal('0.20')", 'sum(values)', False),
        ('median_units', 'What is the median units value for widget rows in months 2 and 3 across all regions?',
         'median', '8', "r['month'] in ('2','3')", 'median(values)', False),
        ('separated_months', 'Add widget units in months 2 and 4 only, across all regions.',
         'sum', '34', "r['month'] in ('2','4')", 'sum(values)', False),
    ]
    result = []
    for name, question, operation, expected, condition, aggregate, supported in definitions:
        code = ("import csv\nfrom decimal import Decimal\nfrom statistics import median\n"
                "with open('data.csv', newline='') as f:\n"
                f"    values=[int(r['units']) for r in csv.DictReader(f) if r['product']=='widget' and {condition}]\n"
                f"print({aggregate})")
        plan = dict(operation=operation, product='widget', first_month=2, last_month=3, region=None)
        result.append(dict(id=name, question=question, expected=expected, json_supported=supported,
                           fixture_json=json.dumps(plan) if supported else 'UNSUPPORTED', fixture_python=code))
    return result
