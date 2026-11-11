"""Conservative, bounded grammar for selecting one writable Python module."""
import re

NAME = r"[A-Za-z_][A-Za-z0-9_]*\.py"
VERB = r"(?:fix|repair|correct|update|edit|modify|change)"
FILE = re.compile(r"\b" + NAME + r"\b")
POSITIVE = [
    re.compile(r"(?:please\s+)?(?:only\s+)?" + VERB +
               r"\s+(?:only\s+)?(?:the\s+)?(?:(?:bugs?\s+in|file|module)\s+)?(" + NAME + r")(?:\s+only|\s+without\s+editing\s+tests|\s+\(do\s+not\s+edit\s+the\s+tests\)\s+until\s+all\s+tests\s+pass)?", re.I),
    re.compile(r"(?:the\s+)?(?:bug|error|defect)\s+is\s+(?:in|inside)\s+(" + NAME + r")", re.I),
    re.compile(r"(?:target|editable)\s+(?:file|module)\s*:\s*(" + NAME + r")", re.I),
]
NEGATIVE = re.compile(r"^(?:please\s+)?(?:do\s+not|don't|never)\s+" + VERB + r"\b", re.I)


def select_coding_target(instruction, code_files):
    """Return one existing target, or None for unsupported/ambiguous directions.

    Recognizes a bounded instruction grammar, not arbitrary English.
    File references in quoted prose and fenced examples are not directives.
    """
    original = instruction
    instruction = re.sub(r"```[\s\S]*?```", " ", instruction)
    instruction = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', " ", instruction)
    instruction = re.sub(r"`(" + NAME + r")`", r"\1", instruction)
    instruction = re.sub(r"(\.py):\s*", r"\1.\n", instruction)
    clauses = re.split(r"(?<=[.!?;])\s+|\n+", instruction)
    requested, forbidden = set(), set()
    unresolved = False
    global_forbidden = False
    for raw in clauses:
        clause = raw.strip().rstrip(".!?;").strip()
        if not clause:
            continue
        names = set(FILE.findall(clause))
        if re.fullmatch(r"run\s+`?python3?\s+test_[A-Za-z0-9_]+\.py`?(?:\s+in\s+the\s+current\s+directory)?", clause, re.I):
            continue
        match = next((m for pattern in POSITIVE if (m := pattern.fullmatch(clause))), None)
        if match:
            requested.add(match.group(1))
            continue
        if NEGATIVE.match(clause):
            if names:
                forbidden.update(names)
            elif not re.fullmatch(r"(?:please\s+)?(?:do\s+not|don't|never)\s+" + VERB + r"\s+(?:the\s+)?(?:tests|dependencies)(?:\s+or\s+(?:tests|dependencies))?", clause, re.I):
                global_forbidden = True
            continue
        if (re.fullmatch(r"leave\s+.+\s+unchanged", clause, re.I)
                or re.search(r"\b(?:read-only|must\s+remain\s+unchanged)\b", clause, re.I)):
            forbidden.update(names)
            if not names and re.search(r"\b(?:both|all|any|code|source)\b", clause, re.I):
                global_forbidden = True
            continue
        if re.fullmatch(r"use\s+" + NAME + r"(?:\s+and\s+never\s+modify\s+dependencies\s+or\s+tests)?", clause, re.I):
            continue
        if names:
            # A dependency reference is not an edit instruction.
            if (not re.search(r"\b" + VERB + r"\b", clause, re.I)
                    and all(re.search(r"\bfrom\s+" + re.escape(n) + r"\b", clause, re.I) for n in names)):
                continue
            unresolved = True
    if global_forbidden or unresolved:
        return None
    by_name = {p.name: p for p in code_files}
    if requested:
        if len(requested) != 1:
            return None
        name = next(iter(requested))
        return by_name.get(name) if name not in forbidden else None
    # Preserve single-module convenience only without named-file directives.
    if len(code_files) == 1 and not FILE.search(original) and not forbidden:
        return code_files[0]
    return None
