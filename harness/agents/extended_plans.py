"""Experimental SalesPlan v2. Strict JSON, exact arithmetic, no generated code.

Representability and valid syntax do not prove a faithful language translation.
Kept separate from v1 so the earlier experiment remains reproducible.
"""
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json

from harness.agents.calculation_plans import decimal_text


@dataclass(frozen=True)
class Predicate:
    column: str
    op: str
    value: str


@dataclass(frozen=True)
class ExtendedSalesPlan:
    operation: str
    product: str
    months: tuple[int, ...]
    region: str | None = None
    predicates: tuple[Predicate, ...] = ()


def number(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Invalid decimal text')
    result = Decimal(value)
    if not result.is_finite() or abs(result.adjusted()) > 1000:
        raise ValueError('Nonfinite or oversized decimal')
    return Fraction(result)


def extended_plan_from_json(text):
    if text.strip() == 'UNSUPPORTED':
        return None

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate field')
            result[key] = value
        return result

    obj = json.loads(text, object_pairs_hook=unique)
    required = {'operation', 'product', 'months'}
    if not isinstance(obj, dict) or not required <= obj.keys() or obj.keys()-required-{'region', 'predicates'}:
        raise ValueError('Invalid schema')
    if obj['operation'] not in ('sum', 'revenue', 'count', 'mean', 'max', 'median'):
        raise ValueError('Invalid operation')
    if not isinstance(obj['product'], str) or not obj['product']:
        raise ValueError('Invalid product')
    months = obj['months']
    if not isinstance(months, list) or not 1 <= len(months) <= 12 or any(type(m) is not int or not 1 <= m <= 12 for m in months):
        raise ValueError('Invalid months')
    if len(set(months)) != len(months):
        raise ValueError('Duplicate month')
    region = obj.get('region')
    if region is not None and (not isinstance(region, str) or not region):
        raise ValueError('Invalid region')
    filters = obj.get('predicates', [])
    if not isinstance(filters, list) or len(filters) > 8:
        raise ValueError('Invalid predicates')
    predicates = []
    for f in filters:
        if not isinstance(f, dict) or set(f) != {'column', 'op', 'value'}:
            raise ValueError('Invalid predicate schema')
        if any(not isinstance(f[k], str) or not f[k] for k in ('column', 'op', 'value')):
            raise ValueError('Invalid predicate values')
        if f['op'] not in ('eq', 'ne', 'gt', 'ge', 'lt', 'le'):
            raise ValueError('Invalid predicate operator')
        if f['op'] not in ('eq', 'ne'):
            number(f['value'])
        predicates.append(Predicate(**f))
    return ExtendedSalesPlan(obj['operation'], obj['product'], tuple(months), region, tuple(predicates))


def predicate_matches(row, predicate):
    value = row[predicate.column]
    if value is None:
        raise ValueError('Missing cell')
    if predicate.op == 'eq': return value == predicate.value
    if predicate.op == 'ne': return value != predicate.value
    left, right = number(value), number(predicate.value)
    return {'gt': left > right, 'ge': left >= right, 'lt': left < right, 'le': left <= right}[predicate.op]


def execute_extended_plan(path, plan):
    required = {'product', 'month'} | {p.column for p in plan.predicates}
    if plan.region is not None: required.add('region')
    if plan.operation != 'count': required.add('units')
    if plan.operation == 'revenue': required.add('price')
    values = []
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            # A model can invent a column: do not infer task impossibility.
            if len(set(fields)) != len(fields) or not required <= set(fields):
                return 'UNKNOWN', None
            for row in reader:
                if None in row: return 'UNKNOWN', None
                if row['product'] != plan.product: continue
                if plan.region is not None and row['region'] != plan.region: continue
                month = int(row['month'])
                if not 1 <= month <= 12: return 'UNKNOWN', None
                if month not in plan.months: continue
                if not all(predicate_matches(row, p) for p in plan.predicates): continue
                value = Fraction(1) if plan.operation == 'count' else number(row['units'])
                if plan.operation == 'revenue': value *= number(row['price'])
                values.append(value)
        if not values and plan.operation in ('mean', 'max', 'median'):
            return 'UNKNOWN', None
        answer = sum(values, Fraction(0))
        if plan.operation == 'mean': answer /= len(values)
        elif plan.operation == 'max': answer = max(values)
        elif plan.operation == 'median':
            values.sort()
            middle = len(values)//2
            answer = values[middle] if len(values)%2 else (values[middle-1]+values[middle])/2
        return 'SOLVED', decimal_text(answer)
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, InvalidOperation, csv.Error):
        return 'UNKNOWN', None
