"""Ультра-экономный солвер для задач типа search (kb/*.md)."""
import re
from pathlib import Path
from typing import Dict

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model
from harness.agents.instruction_scope import question_with_scope
from harness.agents.kb_context import build_kb_context


def _parse_kb(kb_dir: Path) -> Dict[str, dict]:
    """Парсит все markdown файлы в словарь сущностей за 0 токенов."""
    entities: Dict[str, dict] = {}
    for md_file in sorted(kb_dir.glob("*.md")):
        lines = [ln.strip() for ln in md_file.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0].lstrip("#").strip()
        # Exact titles denote the same entity. Merge only compatible fields;
        # preserve every source and conflicting value for later inspection.
        props = entities.setdefault(title, {"_file": md_file.name, "_sources": {}, "_conflicts": {}})
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                key, value = k.strip().lower(), v.strip()
                if not key or key.startswith('_') or not value:
                    continue
                if key in props and props[key] != value:
                    props['_ambiguous'] = '1'
                    conflicts = props['_conflicts'].setdefault(key, {props[key]: list(props['_sources'][key])})
                    sources = conflicts.setdefault(value, [])
                    if md_file.name not in sources:
                        sources.append(md_file.name)
                    continue
                props[key] = value
                sources = props['_sources'].setdefault(key, [])
                if md_file.name not in sources:
                    sources.append(md_file.name)
                if key in props['_conflicts']:
                    props['_conflicts'][key][value] = list(sources)
    return entities


def _resolve_graph_query(instruction, entities):
    """Return (status, answer, evidence) for a fully parsed bounded query.

    None means unsupported language, not an impossible task. Missing facts are
    interpreted under the task's closed KB assumption. No fuzzy entity guesses.
    """
    question = question_with_scope(instruction, r'In which (?:year|city)\b[^?]*\?', 'search')
    if question is None:
        return None
    reference = field = None
    for pattern, target in (
        (r'In which year was (.+) born\?', 'born'),
        (r'In which year was (.+) founded\?', 'founded'),
        (r'In which city is the headquarters of (.+)\?', 'headquarters'),
    ):
        match = re.fullmatch(pattern, question, re.I)
        if match:
            reference, field = match.group(1), target
            break
    if reference is None:
        return None
    parts = reference.replace('\u2019', "'").split("'s ")
    root, relations = parts[0].strip(), [p.strip().lower() for p in parts[1:]]
    if len(relations) > 8 or any(p not in ('mentor', 'employer') for p in relations):
        return None
    evidence = []
    current = root
    for property_name in relations + [field]:
        matches = [name for name in entities if name.casefold() == current.casefold()]
        if not matches:
            return 'UNSOLVABLE', None, f'Missing entity: {current}'
        if len(matches) != 1:
            return 'UNKNOWN', None, f'Ambiguous entity: {current}'
        current = matches[0]
        record = entities[current]
        conflicts = record.get('_conflicts', {})
        if property_name in conflicts or (record.get('_ambiguous') and not conflicts):
            return 'UNKNOWN', None, f'Duplicate/conflicting fields: {current}'
        value = record.get(property_name)
        if not value:
            return 'UNSOLVABLE', None, f'Missing field: {current}.{property_name}'
        files = record.get('_sources', {}).get(property_name, [record['_file']])
        evidence.append(f"{','.join(files)}:{property_name}={value}")
        current = value
    return 'SOLVED', current, ' -> '.join(evidence)


async def solve_search_task(ctx: TaskContext, bridge) -> SolveResult:
    kb_dir = ctx.workspace_dir / "kb"
    if not kb_dir.exists():
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Нет папки kb/")

    entities = _parse_kb(kb_dir)
    if not entities:
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Пустая база kb/")

    q = ctx.instruction

    graph_result = _resolve_graph_query(q, entities)
    if graph_result is not None:
        status, answer, evidence = graph_result
        return SolveResult(task_id=ctx.task_id, status=status, answer=answer, notes=evidence)

    context = build_kb_context(q, entities)
    if not context.names:
        return SolveResult(task_id=ctx.task_id, status="UNKNOWN", notes="No complete KB record fits the context limits")
    model = select_primary_model(ctx)
    refusal = "UNSOLVABLE" if context.complete_kb else "UNKNOWN"
    sys_prompt = (
        "Use ONLY the supplied KB records. Return only the exact requested value without explanation. "
        "Conflicting alternatives are explicitly marked. "
        f"If the answer is unsupported, return {refusal}. Never infer absence from omitted records."
    )
    coverage = "complete" if context.complete_kb else "partial (" + ", ".join(context.limits) + ")"
    user_prompt = f"KB coverage: {coverage}\nKB Records:\n{context.text}\n\nQuestion: {q}"

    ans, in_tok, out_tok, r_tok = await bridge.complete(
        model=model, system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=32
    )
    clean_ans = ans.splitlines()[-1].strip().strip(".") if ans.strip() else ''
    if clean_ans.upper() in ("UNSOLVABLE", "UNKNOWN") or not clean_ans:
        return SolveResult(
            task_id=ctx.task_id,
            status="UNSOLVABLE" if clean_ans.upper() == "UNSOLVABLE" and context.complete_kb else "UNKNOWN",
            notes=f"Model refusal; KB coverage: {coverage}",
            input_tokens=in_tok,
            output_tokens=out_tok,
            reasoning_tokens=r_tok,
            model_used=model,
        )

    return SolveResult(
        task_id=ctx.task_id,
        status="SOLVED",
        answer=clean_ans,
        input_tokens=in_tok,
        output_tokens=out_tok,
        reasoning_tokens=r_tok,
        model_used=model,
    )
