"""Post-hoc E62 generated-code replay with a duplicate right-side row; no API."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.sandbox.executor import run_python_snippet
from multimodule_live import populate,write,digest

def main():
    marker=json.loads((ROOT/'experiments/E61_csv_join/live_started.json').read_text(encoding='utf-8'))
    directory=ROOT/'experiments'/marker['directory']
    responses=[p for p in directory.glob('response_*.json')
               if json.loads(p.read_text(encoding='utf-8'))['task_id']=='inner_filter__multi']
    if len(responses)!=1: raise ValueError('Expected exactly one recorded response')
    response_path=responses[0]
    raw=json.loads(response_path.read_text(encoding='utf-8'))['response']['choices'][0]['message']['content']
    code=re.sub(r'^\x60\x60\x60(?:python)?|\x60\x60\x60$','',raw.strip(),flags=re.MULTILINE).strip()
    case=next(c for c in json.loads((ROOT/'experiments/E61_csv_join/cases.json').read_text(encoding='utf-8')) if c['id']=='inner_filter')
    files=dict(case['files'])
    files['customers.csv']+='A,north\n'
    with sqlite3.connect(':memory:') as connection:
        for name,content in files.items():
            reader=csv.reader(io.StringIO(content))
            columns=next(reader)
            connection.execute('CREATE TABLE "'+Path(name).stem+'" ('+', '.join('"'+c+'" TEXT' for c in columns)+')')
            connection.executemany('INSERT INTO "'+Path(name).stem+'" VALUES ('+','.join('?' for c in columns)+')',list(reader))
        expected=str(connection.execute(case['sql']).fetchone()[0])
    with tempfile.TemporaryDirectory(prefix='oj-join-replay-') as temp:
        populate(Path(temp),files)
        ok,stdout,error=run_python_snippet(code,Path(temp))
    report=dict(scope='Post-hoc metamorphic replay of recorded real model code; not a new generation or independent live task',
                api_calls=0,source_response=response_path.relative_to(ROOT).as_posix(),source_sha256=digest(response_path),
                instruction=case['instruction'],mutation='Append one additional A,north row to customers.csv; unchanged instruction',
                files=files,expected=expected,actual=stdout.strip(),execution_ok=ok,error=error,
                passed=ok and stdout.strip()==expected,
                conclusion='A dictionary keyed by customer_id silently drops multiplicity; fixture correctness does not prove join semantics')
    write(ROOT/'experiments/E63_join_multiplicity_replay.json',report)
    print(json.dumps({k:report[k] for k in ('api_calls','expected','actual','passed')}),flush=True)

if __name__=='__main__': main()
