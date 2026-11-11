"""Experimental lossless table encoding of the SAME selected KB records.

Production search still uses build_kb_context until live evidence and broader
validation justify switching. No fields, sources or conflicting alternatives
are removed by this candidate.
"""
import json
from harness.agents.kb_context import KBContext, build_kb_context

PREFIX = 'JSON table: records=[entity,sources,field values in fields order]; null=missing.\n'

def record_sources(record):
    sources = set()
    for filenames in record.get('_sources', {}).values():
        sources.update(filenames)
    for alternatives in record.get('_conflicts', {}).values():
        for filenames in alternatives.values():
            sources.update(filenames)
    if not sources and record.get('_file'):
        sources.add(record['_file'])
    return sorted(sources)

def table_context(question, entities, **limits):
    baseline = build_kb_context(question, entities, **limits)
    if not baseline.names:
        return baseline
    fields = sorted({key for name in baseline.names for key in entities[name] if not key.startswith('_')})
    rows = []
    for name in baseline.names:
        record = entities[name]
        row = [name, record_sources(record)]
        for field in fields:
            conflicts = record.get('_conflicts', {}).get(field)
            if conflicts:
                row.append({'CONFLICT': sorted(conflicts)})
            else:
                value = record.get(field)
                row.append(value if isinstance(value, str) else None)
        rows.append(row)
    text = PREFIX + json.dumps(dict(fields=fields, records=rows), ensure_ascii=False, separators=(',', ':'))
    # Sparse tables or short contexts may grow; preserve the original verbatim.
    if len(text.encode('utf-8')) >= len(baseline.text.encode('utf-8')):
        return baseline
    return KBContext(text, baseline.names, baseline.complete_kb, baseline.limits)

def decode_table(text):
    """For auditing/round-trip validation only, never used to answer questions."""
    if not text.startswith(PREFIX):
        raise ValueError('Not table-encoded context')
    table = json.loads(text[len(PREFIX):])
    result = {}
    for row in table['records']:
        result[row[0]] = dict(sources=row[1], fields={
            field: value for field, value in zip(table['fields'], row[2:], strict=True) if value is not None})
    return result
