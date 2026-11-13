"""Ordering-only cost medians from E92, frozen before E102/E104/E115.

Never use these values for token reservations or task budget allocation.
Source: E92_final_mixed_live_20261112T185457604685/report.json
SHA256:16434420d43631b4b4ab1055234d7482257c155f1d1df709d17c59d72cd91115
"""
from types import MappingProxyType
MEDIAN_ORDERING_COSTS = MappingProxyType({
    'math':19.0,
    'search':19.3,
    'data_analysis':107.65,
    'coding':100.9,
})
