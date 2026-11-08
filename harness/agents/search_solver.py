"""Ультра-экономный солвер для задач типа search (kb/*.md)."""
import re
from pathlib import Path
from typing import Dict

from harness.config import TaskContext, SolveResult
from harness.agents.model_router import select_primary_model


def _parse_kb(kb_dir: Path) -> Dict[str, Dict[str, str]]:
    """Парсит все markdown файлы в словарь сущностей за 0 токенов."""
    entities: Dict[str, Dict[str, str]] = {}
    for md_file in sorted(kb_dir.glob("*.md")):
        lines = [ln.strip() for ln in md_file.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0].lstrip("#").strip()
        props: Dict[str, str] = {"_file": md_file.name}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                props[k.strip().lower()] = v.strip()
        entities[title] = props
    return entities


async def solve_search_task(ctx: TaskContext, bridge) -> SolveResult:
    kb_dir = ctx.workspace_dir / "kb"
    if not kb_dir.exists():
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Нет папки kb/")

    entities = _parse_kb(kb_dir)
    if not entities:
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Пустая база kb/")

    q = ctx.instruction

    # Попытка 1: Детерминированное разрешение типовых графовых запросов за 0 токенов
    # Шаблон A: "In which year was <Person> born?"
    m_born = re.search(r"In which year was ([A-Z][a-z]+ [A-Z][a-z]+) born\?", q)
    if m_born:
        person = m_born.group(1)
        if person in entities and "born" in entities[person]:
            return SolveResult(
                task_id=ctx.task_id,
                status="SOLVED",
                answer=entities[person]["born"],
                notes="Solved zero-token via KB index",
            )
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes=f"Entity {person} missing")

    # Шаблон B: "In which city is the headquarters of <Person>'s employer?"
    m_hq = re.search(r"headquarters of ([A-Z][a-z]+ [A-Z][a-z]+)'s employer", q)
    if m_hq:
        person = m_hq.group(1)
        if person in entities:
            emp = entities[person].get("employer", "")
            if emp in entities and "headquarters" in entities[emp]:
                return SolveResult(
                    task_id=ctx.task_id,
                    status="SOLVED",
                    answer=entities[emp]["headquarters"],
                    notes="Solved 2-hop zero-token via KB index",
                )
        return SolveResult(task_id=ctx.task_id, status="UNSOLVABLE", notes="Broken 2-hop link in KB")

    # Попытка 2: Если вопрос нестандартный, отбираем только релевантные карточки (1-hop и 2-hop) и подаём в noreason LLM
    relevant_Names = [name for name in entities if name.lower() in q.lower()]
    expanded = set(relevant_Names)
    for name in list(expanded):
        for val in entities[name].values():
            if val in entities:
                expanded.add(val)

    if not expanded:
        snippets = [f"# {k}: {v}" for k, v in list(entities.items())[:15]]
    else:
        snippets = [f"# {k}: {entities[k]}" for k in sorted(expanded)]

    model = select_primary_model(ctx)
    sys_prompt = (
        "Answer the user question using ONLY the provided KB records. "
        "Output ONLY the exact final value (single number, name, or city) without punctuation or explanation. "
        "If the information is missing or contradictory, output UNSOLVABLE."
    )
    user_prompt = f"KB Records:\n" + "\n".join(snippets) + f"\n\nQuestion: {q}"

    ans, in_tok, out_tok, r_tok = await bridge.complete(
        model=model, system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=32
    )
    clean_ans = ans.splitlines()[-1].strip().strip(".")
    if "UNSOLVABLE" in clean_ans.upper() or not clean_ans:
        return SolveResult(
            task_id=ctx.task_id,
            status="UNSOLVABLE",
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
