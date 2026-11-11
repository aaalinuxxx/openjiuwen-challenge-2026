"""Validate generated labels with separate oracles; never uses API."""
import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = {
 'average': 'def average(xs): return sum(xs)/len(xs) if xs else 0\n',
 'count_even': 'def count_even(xs): return len([x for x in xs if not x%2])\n',
 'stable_unique': 'def stable_unique(xs): return list(dict.fromkeys(xs))\n',
 'rotate': 'def rotate(xs): return xs[-1:]+xs[:-1]\n',
}

def oracle(task, directory):
    kind, question = task['task_type'], task['instruction']
    work = directory/'workspace'
    if kind == 'math':
        current = int(re.search(r'starts with (\d+) boxes', question)[1])
        pattern = (r'split equally into (\d+) warehouses|stock is doubled|'
                   r'ships (\d+) boxes per day for (\d+) days|receives (\d+) deliveries of (\d+) boxes')
        for match in re.finditer(pattern, question):
            if match[1] is not None:
                if int(match[1]) == 0: return 'UNSOLVABLE'
                current //= int(match[1])
            elif match[2] is not None: current -= int(match[2])*int(match[3])
            elif match[4] is not None: current += int(match[4])*int(match[5])
            else: current *= 2
        return str(current)
    if kind == 'data_analysis':
        with (work/'sales.csv').open(encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            if not {'product','month','units'} <= set(reader.fieldnames or []):
                return 'UNSOLVABLE'
            match = re.search(r"product '([^']+)' were sold in months (\d+) through (\d+)", question)
            return str(sum(int(row['units']) for row in reader if row['product'] == match[1]
                           and int(match[2]) <= int(row['month']) <= int(match[3])))
    if kind == 'search':
        records = {}
        for file in (work/'kb').glob('*.md'):
            lines = file.read_text(encoding='utf-8').splitlines()
            records[lines[0].lstrip('# ')] = dict(line.split(': ',1) for line in lines[1:] if ': ' in line)
        born = re.search(r'In which year was (.+?) born\?', question)
        if born:
            return records.get(born[1], {}).get('Born', 'UNSOLVABLE')
        employer = re.search(r"headquarters of (.+?)'s employer\?", question)
        company = records.get(employer[1], {}).get('Employer')
        return records.get(company, {}).get('Headquarters', 'UNSOLVABLE')
    if kind == 'coding':
        family = task.get('family')
        if family == 'pure_function_conflict':
            if 'pure' not in question or 'deterministic' not in question:
                raise ValueError('Conflict requires explicit purity contract')
            values = {}
            for node in ast.walk(ast.parse((work/'test_mylib.py').read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'assertEqual':
                    key, value = ast.unparse(node.args[0]), ast.unparse(node.args[1])
                    if key in values and values[key] != value: return 'UNSOLVABLE'
                    values[key] = value
            raise ValueError('Missing specified conflict')
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'work'
            shutil.copytree(work, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (target/'mylib.py').write_text(REFERENCES[family], encoding='utf-8')
            for test in target.glob('test_*.py'):
                result = subprocess.run([sys.executable, '-B', test.name], cwd=target, capture_output=True, timeout=8)
                if result.returncode: raise ValueError('Reference failed generated tests')
        return 'DONE'
    raise ValueError('Unknown type')


def validate(source):
    tasks = sorted(source.glob('*/task.json'))
    if not tasks: raise ValueError('No tasks')
    rows = []
    for path in tasks:
        task = json.loads(path.read_text(encoding='utf-8'))
        expected = oracle(task, path.parent)
        rows.append(dict(task_id=task['task_id'], task_type=task['task_type'],
            family=task.get('family'), oracle=expected, expected=task['expected'],
            label_valid=expected == str(task['expected']) and task['unsolvable'] == (expected == 'UNSOLVABLE')))
    return rows

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks-dir', type=Path, required=True)
    args = parser.parse_args()
    rows = validate(args.tasks_dir)
    report = dict(scope='generator consistency using independent arithmetic/CSV/KB oracles and coding references',
        api_calls=0, total=len(rows), valid=sum(r['label_valid'] for r in rows), rows=rows,
        source_hashes={p.relative_to(args.tasks_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in args.tasks_dir.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
    path = ROOT/'experiments'/('E34_dataset_validation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_hashes')}))
    print('Report:', path)
    if report['valid'] != report['total']: raise SystemExit(1)
