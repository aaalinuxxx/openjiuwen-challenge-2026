"""Counterexamples for H03.3/H04.3/H04.4; no API or model-quality claims.

Cases and independent answers are frozen before changing the solvers. DEFER
means a conservative handoff is acceptable, not that the task is impossible.
"""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import TaskContext
from harness.agents.data_solver import solve_data_task
from harness.agents.math_solver import solve_math_task
from harness.agents.search_solver import solve_search_task


class NeedsAPI(Exception):
    pass


class Offline:
    async def complete(self, **kwargs):
        raise NeedsAPI()


def cases():
    rng = random.Random(11011)
    specs = []
    for i in range(8):
        born = rng.randint(1960, 1990)
        units, other = rng.randint(10, 30), rng.randint(40, 70)
        query = "In which year was Ada Stone born?"
        base = {'kb/a.md': f'# Ada Stone\nBorn: {born}\n'}

        def add(family, group, kind, instruction, files, expected, wanted='SOLVED'):
            specs.append(dict(id=f'{family}_{i}', family=family, group=group,
                              kind=kind, instruction=instruction, files=files,
                              expected=None if expected is None else str(expected), wanted=wanted))

        add('duplicate_identical', 'duplicates', 'search', query,
            {**base, 'kb/b.md': base['kb/a.md']}, born)
        add('duplicate_complementary', 'duplicates', 'search', query,
            {'kb/a.md': '# Ada Stone\nEmployer: Orbit\n', 'kb/b.md': base['kb/a.md']}, born)
        add('duplicate_chain', 'duplicates', 'search',
            "In which city is the headquarters of Ada Stone's employer?",
            {**base, 'kb/b.md': '# Ada Stone\nEmployer: Orbit\n',
             'kb/c.md': '# Orbit\nFounded: 2000\n', 'kb/d.md': '# Orbit\nHeadquarters: Lima\n'}, 'Lima')
        add('conflicting_duplicates', 'duplicates', 'search', query,
            {**base, 'kb/b.md': f'# Ada Stone\nBorn: {born+1}\n'}, None, 'DEFER')
        add('conflicting_single_card', 'duplicates', 'search', query,
            {'kb/a.md': base['kb/a.md']+f'Born: {born+1}\n'}, None, 'DEFER')
        add('case_collision', 'duplicates', 'search', query,
            {**base, 'kb/b.md': f'# ADA STONE\nBorn: {born+1}\n'}, None, 'DEFER')

        table = f'product,region,month,units\nwidget,north,2,{units}\nwidget,south,2,{other}\n'
        q = "How many units of product 'widget' were sold in months 2 through 3 inclusive?"
        add('csv_control', 'context', 'data_analysis', q+' Write ONLY the answer to answer.txt.',
            {'sales.csv': table}, units+other)
        add('csv_prefix_constraint', 'context', 'data_analysis', 'Consider only the north region. '+q,
            {'sales.csv': table}, units, 'DEFER')
        add('csv_suffix_constraint', 'context', 'data_analysis', q+' Count only rows from the north region.',
            {'sales.csv': table}, units, 'DEFER')
        add('csv_write_constraint', 'context', 'data_analysis',
            q+' Write ONLY the answer for the north region to answer.txt.', {'sales.csv': table}, units, 'DEFER')
        math = f'A warehouse starts with {units} boxes. It receives {other} boxes. How many boxes does it have at the end?'
        add('math_control', 'context', 'math', math+' Write ONLY the answer to answer.txt.', {}, units+other)
        add('math_compute_constraint', 'context', 'math', math+' Compute it after subtracting 5 damaged boxes.',
            {}, units+other-5, 'DEFER')
        add('math_write_constraint', 'context', 'math', math+' Write ONLY half of the final stock to answer.txt.',
            {}, (units+other)/2, 'DEFER')
        company = {'kb/a.md': '# Orbit\nHeadquarters: Lima\n'}
        hq = 'In which city is the headquarters of Orbit?'
        add('search_control', 'context', 'search', hq+' Write ONLY the answer to answer.txt.', company, 'Lima')
        add('search_prefix_constraint', 'context', 'search', 'Use the location as of 1999. '+hq,
            company, None, 'DEFER')
        add('search_suffix_constraint', 'context', 'search', hq+' Use the location as of 1999.',
            company, None, 'DEFER')
        for filename in ('a.csv', 'z.csv'):
            otherfile = 'z.csv' if filename == 'a.csv' else 'a.csv'
            files = {filename: table, otherfile: 'product,region,month,units\nwidget,north,2,9999\n'}
            add('csv_named_'+filename[0], 'files', 'data_analysis',
                f'The file {filename} has columns product,region,month,units (2 rows). '+q, files, units+other)
        add('csv_ambiguous_file', 'files', 'data_analysis', q,
            {'a.csv': table, 'z.csv': 'product,region,month,units\nwidget,north,2,9999\n'}, None, 'DEFER')
        add('csv_named_missing', 'files', 'data_analysis',
            'The file absent.csv has columns product,region,month,units (2 rows). '+q,
            {'sales.csv': table}, None, 'UNSOLVABLE')
    return specs


async def run(label):
    specs, rows = cases(), []
    with tempfile.TemporaryDirectory(prefix='oj-robustness-') as tmp:
        for spec in specs:
            folder = Path(tmp)/spec['id']
            folder.mkdir()
            for name, content in spec['files'].items():
                path = folder/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            # The solver receives no reference answers or behavior labels.
            ctx = TaskContext(spec['id'], spec['kind'], spec['instruction'], 1, folder, folder, 0, False)
            try:
                solver = {'search': solve_search_task, 'data_analysis': solve_data_task, 'math': solve_math_task}[spec['kind']]
                result = await solver(ctx, Offline())
                status, answer = result.status, result.answer
            except NeedsAPI:
                status, answer = 'NEEDS_API', None
            except Exception as exc:
                status, answer = 'ERROR_'+type(exc).__name__, None
            solved = status == 'SOLVED' and answer == spec['expected'] and spec['expected'] is not None
            correct = solved if spec['wanted'] == 'SOLVED' else (
                status == 'UNSOLVABLE' if spec['wanted'] == 'UNSOLVABLE' else status in ('UNKNOWN', 'NEEDS_API') or solved)
            rows.append(dict(task_id=spec['id'], family=spec['family'], group=spec['group'],
                             wanted=spec['wanted'], expected_answer=spec['expected'], status=status, answer=answer,
                             correct_behavior=correct, solved_correct=solved,
                             wrong_answer=status == 'SOLVED' and not solved))

    def summarize(selected):
        return dict(total=len(selected), correct_behavior=sum(r['correct_behavior'] for r in selected),
                    solved_correct=sum(r['solved_correct'] for r in selected),
                    wrong_answers=sum(r['wrong_answer'] for r in selected),
                    statuses=dict(Counter(r['status'] for r in selected)))

    sources = list((ROOT/'harness').rglob('*.py'))+[Path(__file__)]
    report = dict(label=label, seed=11011, scope='synthetic adversarial dev; conservative deferrals are not solved tasks',
                  api_calls=0, summary=summarize(rows),
                  groups={g: summarize([r for r in rows if r['group'] == g]) for g in ('duplicates', 'context', 'files')},
                  dataset_sha256=hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest(),
                  source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                  rows=rows)
    with (ROOT/'experiments'/f'{label}.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(summary=report['summary'], groups=report['groups'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not args.label.replace('_', '').isalnum():
        parser.error('Invalid label')
    asyncio.run(run(args.label))
