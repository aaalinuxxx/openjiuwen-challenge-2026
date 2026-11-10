"""Experimental warning signals for SalesPlan expressivity, NOT a proof.

Empty risks means no known signal was found, not that the question is faithfully
represented. This gate is used only by replay experiments, not production.
"""
import re


def json_plan_risks(question, columns):
    reasons = []
    represented = {'product', 'region', 'month', 'units', 'price'}
    for column in sorted(set(columns) - represented):
        if re.search(r'(?<!\w)'+re.escape(column)+r'(?!\w)', question, re.I):
            reasons.append('unrepresented_column:'+column)
    signals = {
        'exclusion': r'\b(?:exclude|excluding|except|without|nonrefunded|non-refunded)\b',
        'unsupported_aggregate': r'\b(?:median|variance|deviation|percentile|distinct|unique)\b',
        'group_or_join': r'\b(?:group(?:ed)? by|for each|per region|join|merge)\b',
        'numeric_predicate': r'(?:[<>]=?|\b(?:above|below|at least|at most|greater than|less than)\b)',
        'rounding': r'\b(?:round(?:ed)?|decimal places)\b',
    }
    for name, pattern in signals.items():
        if re.search(pattern, question, re.I):
            reasons.append(name)
    for match in re.finditer(r'\bmonths?\s+(\d+)\s+(?:and|or)\s+(\d+)\b', question, re.I):
        if abs(int(match[1])-int(match[2])) > 1:
            reasons.append('noncontiguous_months')
    return reasons
