"""Experimental evidence-bearing search output; not general NL proof."""
from collections import Counter
import json
import re

from harness.config import SolveResult
from harness.agents.search_solver import _parse_kb
from harness.agents.kb_context import build_kb_context
from harness.agents.model_router import select_primary_model


def _mentioned(name, question):
    return re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)', question, re.I) is not None


def verify_evidence(question, entities, selected_names, complete_kb, document):
    """Check factual/path support, with deliberately limited question matching.

    Field aliases and relation counts do NOT prove arbitrary natural-language
    scope, relationship order, temporal qualifiers, negation or multi-intent.
    """
    def unknown(reason): return 'UNKNOWN', None, reason
    if not isinstance(document, dict) or set(document) != {'status','answer','evidence'}:
        return unknown('Invalid response schema')
    status, answer, evidence = document['status'], document['answer'], document['evidence']
    if not isinstance(status,str) or status not in ('SOLVED','UNKNOWN','UNSOLVABLE'):
        return unknown('Invalid status')
    if status == 'SOLVED':
        if not isinstance(answer,str) or not answer.strip():
            return unknown('Missing final answer')
    elif answer is not None:
        return unknown('Refusal must have null answer')
    if not isinstance(evidence,list) or not 1 <= len(evidence) <= 9:
        return unknown('Missing or excessive evidence')
    anchors=[name for name in entities if _mentioned(name,question)]
    if len(anchors)!=1: return unknown('Question root not unique')
    targets=[field for field,pattern in (
        ('headquarters',r'\b(?:headquarters|HQ)\b'),
        ('born',r'\b(?:born|birth)\b'),
        ('founded',r'\bfounded\b'),
        ('title',r'\btitle\b')) if re.search(pattern,question,re.I)]
    if len(targets)!=1: return unknown('Unsupported or ambiguous requested field')
    target=targets[0]
    required=Counter(re.findall(r'\b(?:mentor|employer)\b',question.lower()))
    used=Counter()
    current=anchors[0]
    trail=[]
    for i,pointer in enumerate(evidence):
        if not isinstance(pointer,list) or len(pointer)!=2 or not all(isinstance(v,str) for v in pointer):
            return unknown('Invalid field pointer')
        name,field=pointer
        if name!=current or name not in selected_names or name not in entities:
            return unknown('Unseen entity or disconnected evidence path')
        record=entities[name]
        is_last=i==len(evidence)-1
        terminal=field==target
        if terminal:
            if not is_last or used!=required:
                return unknown('Incomplete relationship evidence')
        else:
            if field not in required or used[field]>=required[field]:
                return unknown('Unrequested relation')
            used[field]+=1
        conflict=record.get('_conflicts',{}).get(field)
        if conflict:
            if status=='SOLVED': return unknown('Cited field is contradictory')
            # Intermediate contradictions can converge later: do not call
            # them a proof of task impossibility.
            if terminal and complete_kb and status=='UNSOLVABLE':
                return 'UNSOLVABLE',None,'Conflicting requested values: '+name+'.'+field
            return unknown('Conflicting intermediate evidence')
        if field not in record:
            if is_last and complete_kb and status=='UNSOLVABLE':
                return 'UNSOLVABLE',None,'Missing requested path field: '+name+'.'+field
            return unknown('Missing field without complete refusal proof')
        value=record[field]
        if not isinstance(value,str): return unknown('Nontext KB field')
        sources=record.get('_sources',{}).get(field,[])
        trail.append(dict(entity=name,field=field,value=value,sources=sources))
        if terminal:
            if status!='SOLVED': return unknown('Refusal despite cited available value')
            if answer!=value: return unknown('Answer differs from cited value')
            return 'SOLVED',answer,'Checked field path: '+json.dumps(trail,ensure_ascii=False)
        if is_last: return unknown('Evidence does not reach requested field')
        next_names=[name for name in entities if name.casefold()==value.casefold()]
        if len(next_names)!=1: return unknown('Missing or ambiguous relation target')
        current=next_names[0]
    return unknown('No terminal evidence')


async def solve_evidence_search(ctx, bridge):
    entities=_parse_kb(ctx.workspace_dir/'kb')
    context=build_kb_context(ctx.instruction,entities)
    if not context.names:
        return SolveResult(task_id=ctx.task_id,status='UNKNOWN',notes='No KB context')
    system=(
        'Use only the supplied KB. Return one JSON object, no markdown, with exactly keys '
        '"status","answer","evidence". status is SOLVED, UNKNOWN, or UNSOLVABLE. '
        'answer is the exact requested value for SOLVED, otherwise null. '
        'evidence is an ordered path of [entity,field] pointers starting at the entity in the question, '
        'following relations and ending at the requested field. Use exact entity names and lowercase fields. '
        'For missing or contradictory facts, include the path up to that field and refuse; never choose one '
        'conflicting alternative. Ignore conflicts in unrelated fields. '
        'Use UNSOLVABLE only if the supplied complete KB proves the requested value missing or contradictory; '
        'otherwise use UNKNOWN. A literal value CONFLICT may be a valid answer.'
    )
    coverage='complete' if context.complete_kb else 'partial'
    user=f'KB coverage: {coverage}\nKB Records:\n{context.text}\n\nQuestion: {ctx.instruction}'
    raw,inp,out,reason=await bridge.complete(
        model=select_primary_model(ctx),system_prompt=system,user_prompt=user,max_tokens=192)
    try:
        document=json.loads(raw)
    except (ValueError,TypeError):
        result=('UNKNOWN',None,'Invalid JSON response')
    else:
        result=verify_evidence(ctx.instruction,entities,context.names,context.complete_kb,document)
    return SolveResult(task_id=ctx.task_id,status=result[0],answer=result[1],notes=result[2],
                       input_tokens=inp,output_tokens=out,reasoning_tokens=reason,
                       model_used=select_primary_model(ctx))
