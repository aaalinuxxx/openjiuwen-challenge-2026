from decimal import Decimal, ROUND_HALF_UP
from a_rates import RATES

def total(rows):
    value = sum((Decimal(str(amount)) for amount, currency in rows), Decimal('0'))
    return format(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'f')
