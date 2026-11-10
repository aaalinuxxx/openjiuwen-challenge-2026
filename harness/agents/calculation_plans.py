"""Small typed plans with deterministic execution; no eval/generated code."""
import csv
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re
from harness.agents.instruction_scope import administrative_tail, question_with_scope


@dataclass(frozen=True)
class SalesPlan:
    operation: str
    product: str
    first_month: int
    last_month: int
    region: str | None = None


def sales_plan_from_json(text):
    """Strict experimental LLM boundary. None denotes explicit UNSUPPORTED.

    Extra/duplicate fields are errors: dropping a filter would change the task.
    This decoder is not yet enabled as the production solver's fallback.
    """
    if text.strip() == 'UNSUPPORTED':
        return None

    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON field')
            obj[key] = value
        return obj

    obj = json.loads(text, object_pairs_hook=unique_object)
    required = {'operation', 'product', 'first_month', 'last_month'}
    if not isinstance(obj, dict) or not required <= obj.keys() or obj.keys() - required - {'region'}:
        raise ValueError('Invalid plan schema')
    if type(obj['operation']) is not str or obj['operation'] not in ('sum', 'revenue', 'count', 'mean', 'max'):
        raise ValueError('Invalid operation')
    if type(obj['product']) is not str or not obj['product']:
        raise ValueError('Invalid product')
    if obj.get('region') is not None and (type(obj['region']) is not str or not obj['region']):
        raise ValueError('Invalid region')
    if any(type(obj[k]) is not int for k in ('first_month', 'last_month')):
        raise ValueError('Months must be integers')
    if not 1 <= obj['first_month'] <= obj['last_month'] <= 12:
        raise ValueError('Invalid month range')
    return SalesPlan(**obj)


def parse_sales_plan(instruction):
    question=question_with_scope(instruction,r'(?:How many|What is)\b[^?]*\?','sales')
    if question is None: return None
    product=r"product '([^']+)'(?: in region '([^']+)')?"
    months=r'months (\d+) through (\d+) inclusive\?'
    patterns=[
        (rf'How many units of {product} were sold in {months}','sum'),
        (rf'What is the total revenue from {product} sold in {months}','revenue'),
        (rf'How many rows for {product} are in {months}','count'),
        (rf'What is the average units per row for {product} in {months}','mean'),
        (rf'What is the maximum units per row for {product} in {months}','max')]
    for pattern,op in patterns:
        m=re.fullmatch(pattern,question,re.I)
        if m:
            name,region,lo,hi=m.groups()
            lo,hi=int(lo),int(hi)
            if not 1<=lo<=hi<=12: return None
            return SalesPlan(op,name,lo,hi,region)
    return None


def decimal_text(value):
    denominator=value.denominator
    powers=[]
    for divisor in (2,5):
        power=0
        while denominator%divisor==0:
            denominator//=divisor
            power+=1
        powers.append(power)
    if denominator!=1: raise ValueError('Nonterminating decimal')
    scale=max(powers)
    if not scale: return str(value.numerator)
    number=abs(value.numerator)*10**scale//value.denominator
    digits=str(number).zfill(scale+1)
    result=(digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.')
    return ('-' if value<0 else '')+result


def execute_sales_plan(path,plan):
    """(status, value). Bad numbers/ambiguous aggregates remain UNKNOWN."""
    if plan.operation not in ('sum','revenue','count','mean','max'):
        raise ValueError('Unsupported plan operation')
    required={'product','month'}
    if plan.region is not None: required.add('region')
    if plan.operation!='count': required.add('units')
    if plan.operation=='revenue': required.add('price')
    values=[]
    try:
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            fields=reader.fieldnames or []
            if not required.issubset(fields): return 'UNSOLVABLE',None
            if len(set(fields))!=len(fields): return 'UNKNOWN',None
            for row in reader:
                if row.get('product')!=plan.product: continue
                if plan.region is not None and row.get('region')!=plan.region: continue
                month=int(row['month'])
                if not 1<=month<=12: return 'UNKNOWN',None
                if not plan.first_month<=month<=plan.last_month: continue
                number=Decimal(1) if plan.operation=='count' else Decimal(row['units'])
                if not number.is_finite(): return 'UNKNOWN',None
                value=Fraction(number)
                if plan.operation=='revenue':
                    price=Decimal(row['price'])
                    if not price.is_finite(): return 'UNKNOWN',None
                    value*=Fraction(price)
                values.append(value)
    except (ValueError,TypeError,InvalidOperation,UnicodeError,csv.Error):
        return 'UNKNOWN',None
    if not values and plan.operation in ('mean','max'): return 'UNKNOWN',None
    answer=sum(values,Fraction(0))
    if plan.operation=='mean':
        # Do not invent a rounding rule for a nonterminating decimal.
        exact=answer/len(values)
        denominator=exact.denominator
        for divisor in (2,5):
            while denominator%divisor==0: denominator//=divisor
        if denominator!=1: return 'UNKNOWN',None
        answer/=len(values)
    elif plan.operation=='max': answer=max(values)
    return 'SOLVED',decimal_text(answer)


@dataclass(frozen=True)
class WarehousePlan:
    initial: int
    operations: tuple


def parse_warehouse_plan(instruction):
    question='How many boxes does it have at the end?'
    if instruction.count(question)!=1: return None
    body,tail=instruction.split(question)
    # Only operational output instructions may follow the question.
    # Each segment must be recognized; unknown arithmetic is never skipped.
    if not administrative_tail(tail): return None
    sentences=[s.strip() for s in re.split(r'\.\s+|\.$',body.strip()) if s.strip()]
    if not sentences: return None
    start=re.fullmatch(r'A warehouse starts with (\d+) boxes',sentences[0])
    if not start: return None
    operations=[]
    for sentence in sentences[1:]:
        if sentence=='Then the stock is doubled by merging with a sister warehouse':
            operations.append(('multiply',2)); continue
        m=re.fullmatch(r'Then the stock is split equally into (\d+) warehouses and it keeps one share \(rounded down\)',sentence)
        if m: operations.append(('floor_divide',int(m[1]))); continue
        m=re.fullmatch(r'It ships (\d+) boxes per day for (\d+) days',sentence)
        if m: operations.append(('add',-int(m[1])*int(m[2]))); continue
        m=re.fullmatch(r'It receives (\d+) deliveries of (\d+) boxes each',sentence)
        if m: operations.append(('add',int(m[1])*int(m[2]))); continue
        m=re.fullmatch(r'It (ships|receives) (\d+) boxes',sentence)
        if m: operations.append(('add',int(m[2])*(-1 if m[1]=='ships' else 1))); continue
        return None
    return WarehousePlan(int(start[1]),tuple(operations))


def execute_warehouse_plan(plan):
    value=plan.initial
    for operation,argument in plan.operations:
        if operation=='add': value+=argument
        elif operation=='multiply': value*=argument
        elif operation=='floor_divide':
            if argument==0: return 'UNSOLVABLE'
            value//=argument
        else: raise ValueError('Unsupported operation')
    return str(value)
