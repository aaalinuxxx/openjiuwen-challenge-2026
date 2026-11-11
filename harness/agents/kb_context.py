"""Bounded context assembly over parsed KB records; no LLM or fuzzy entity matching."""
from collections import deque
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class KBContext:
    text: str
    names: tuple[str, ...]
    complete_kb: bool
    limits: tuple[str, ...]


def _values(record, field):
    conflicts=record.get('_conflicts', {}).get(field)
    if conflicts:
        return sorted(conflicts)
    value=record.get(field)
    return [value] if isinstance(value,str) else []


def _render(name, record):
    fields=sorted(k for k in record if not k.startswith('_'))
    sources=set()
    for filenames in record.get('_sources',{}).values():
        sources.update(filenames)
    for conflicts in record.get('_conflicts',{}).values():
        for filenames in conflicts.values():
            sources.update(filenames)
    if not sources and record.get('_file'):
        sources.add(record['_file'])
    lines=['# '+name]
    if sources: lines.append('Sources: '+', '.join(sorted(sources)))
    for field in fields:
        values=_values(record,field)
        if field in record.get('_conflicts',{}):
            lines.append(field+': CONFLICT ['+' | '.join(values)+']')
        elif values:
            lines.append(field+': '+values[0])
    return '\n'.join(lines)


def build_kb_context(question, entities, max_hops=3, max_records=32, max_bytes=12000):
    if any(type(v) is not int for v in (max_hops,max_records,max_bytes)) or max_hops<0 or max_records<1 or max_bytes<1:
        raise ValueError('Invalid KB context limits')
    ordered=sorted(entities,key=lambda name:(name.casefold(),name))
    by_fold={}
    for name in ordered:
        by_fold.setdefault(name.casefold(),[]).append(name)
    roots=[name for name in ordered if re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',question,re.I)]
    # If no entity is mentioned, deterministic bounded whole-KB inspection.
    queue=deque((name,0) for name in (roots or ordered))
    seen=set(name for name,_ in queue)
    selected=[];blocks=[];used=0;limits=set()
    while queue:
        if len(selected)>=max_records:
            limits.add('record_limit')
            break
        name,depth=queue.popleft()
        record=entities[name]
        block=_render(name,record)
        size=len(block.encode('utf-8'))+(2 if blocks else 0)
        if used+size>max_bytes:
            limits.add('byte_limit')
            continue
        selected.append(name);blocks.append(block);used+=size
        neighbors=set()
        for field in record:
            if field.startswith('_'): continue
            for value in _values(record,field):
                neighbors.update(by_fold.get(value.casefold(),[]))
        for other in sorted(neighbors,key=lambda value:(value.casefold(),value)):
            if other in seen: continue
            if depth>=max_hops:
                limits.add('depth_limit')
                continue
            seen.add(other)
            queue.append((other,depth+1))
    complete=len(selected)==len(entities)
    if not complete: limits.add('partial_kb')
    return KBContext('\n\n'.join(blocks),tuple(selected),complete,tuple(sorted(limits)))
