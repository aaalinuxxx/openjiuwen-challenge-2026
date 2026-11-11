"""Conservative scope checks for local parsers, not general language parsing.

Unknown surrounding prose must reach a language-model fallback instead of
being silently discarded. Only explicitly known administrative clauses pass.
"""
import re


SALES_PREFIX = re.compile(
    r'The file ([A-Za-z0-9_-][A-Za-z0-9_.-]*\.csv) has columns '
    r'[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)* '
    r'\(\d+ rows\)\.', re.I)

ADMINISTRATIVE = (
    'When you are done, write ONLY the final answer to the file answer.txt in the current directory',
    'Write ONLY the answer to answer.txt',
    'Write ONLY the final answer to answer.txt',
    'Use bash with python3 to compute it',
    'Compute it with the bash tool (python3 -c)',
    'Compute it with Python',
    'Work only inside the current directory',
    'Use the file tools or bash (ls, grep, cat) to find it',
    'When you are done, write ONLY the final answer to answer.txt in the current directory',
    'When you are done, write ONLY the final answer to the file answer.txt in the current directory '
    '(for example with bash: echo 42 > answer.txt)',
)


def administrative_tail(text):
    text = ' '.join(text.split())
    sentences = [s.strip() for s in re.split(r'\.\s+|\.$', text) if s.strip()]
    allowed = {clause.casefold() for clause in ADMINISTRATIVE}
    return all(s.casefold() in allowed and
               ('answer.txt' not in s.casefold() or 'answer.txt' in s)
               for s in sentences)


def question_with_scope(instruction, pattern, kind):
    matches = list(re.finditer(pattern, instruction, re.I))
    if len(matches) != 1:
        return None
    match = matches[0]
    prefix = ' '.join(instruction[:match.start()].split())
    if kind == 'sales':
        prefix_ok = not prefix or SALES_PREFIX.fullmatch(prefix) is not None
    elif kind == 'search':
        prefix_ok = prefix in ('', 'The directory kb/ contains markdown records.',
                              'The directory kb/ contains a small knowledge base of markdown files.')
    else:
        raise ValueError('Unsupported scope')
    if not prefix_ok or not administrative_tail(instruction[match.end():]):
        return None
    return match.group(0)


def sales_source_name(instruction):
    """Return a named input only from the recognized metadata prefix."""
    match = SALES_PREFIX.match(' '.join(instruction.split()))
    return match[1] if match is not None else None
