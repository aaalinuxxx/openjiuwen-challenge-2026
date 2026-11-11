"""Run the frozen E41 challenge without exposing its external oracles to solvers."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from main_offline_benchmark import run, parse_args, ROOT, hashes

FIXTURE=ROOT/'experiments'/'E41_family_shift'

async def execute(options):
    manifest=json.loads((FIXTURE/'manifest.json').read_text(encoding='utf-8'))
    current=hashes(FIXTURE/'tasks')
    if current != manifest['fixtures_sha256']:
        raise ValueError('Frozen input hashes changed')
    phase=options.phase
    live=phase!='offline'
    if live and not options.live:
        raise ValueError('Paid phases require --live explicitly')
    if not live and options.live:
        raise ValueError('Offline phase cannot use --live')
    limits={'offline':(0,1,'E42_family_offline'),
            'noncoding':(3000,12,'E43_family_noncoding_live'),
            'coding':(2000,6,'E44_family_coding_live')}
    budget,calls,label=limits[phase]
    if options.replay:
        if live: raise ValueError('Replay option is offline only; new paid comparisons need a separate plan')
        label='E45_family_offline_replay'
    if options.profile == 'spacious':
        if phase != 'noncoding': raise ValueError('Spacious profile is a noncoding comparison only')
        label = 'E46_family_spacious_live'
    previous=list((ROOT/'experiments').glob(label+'_*'))
    if live and previous:
        raise ValueError('This paid phase was already started; inspect its saved ledger instead of repeating it')
    if live:
        for p in (ROOT/'experiments').glob('E4[34]_family_*_live_*/budget.json'):
            if json.loads(p.read_text())['has_unaccounted_request']:
                raise ValueError('Earlier phase has unknown cost; no more live calls')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    control=ROOT/'experiments'/f'{label}_control_{stamp}.json'
    record=dict(profile=options.profile,phase=phase,status='STARTED',live=live,budget=budget,max_calls=calls,
        scope='prospective authored family-shift challenge; dev replay' if options.replay else
              'first evaluation of frozen authored challenge; not external blind holdout',
        fixture_manifest_sha256=hashlib.sha256((FIXTURE/'manifest.json').read_bytes()).hexdigest(),
        solver_hashes=hashes(ROOT/'harness'))
    control.write_text(json.dumps(record,indent=2),encoding='utf-8')
    try:
        with tempfile.TemporaryDirectory(prefix='oj-family-selection-') as temp:
            selected=Path(temp)/'tasks';selected.mkdir()
            for task in sorted((FIXTURE/'tasks').glob('*/task.json')):
                meta=json.loads(task.read_text(encoding='utf-8'))
                if phase=='coding' and meta['task_type']!='coding': continue
                if phase=='noncoding' and meta['task_type']=='coding': continue
                shutil.copytree(task.parent,selected/task.parent.name)
            argv=['--tasks-dir',str(selected),'--label',label,'--budget',str(budget),'--max-calls',str(calls)]
            if options.profile == 'spacious':
                argv+=['--search-min-budget','600','--data-min-budget','600']
            if live: argv+=['--live']
            report=await run(parse_args(argv))
        if hashes(FIXTURE/'tasks')!=current: raise AssertionError('Frozen inputs changed')
        false_refusals=[r['task_id'] for r in report['rows']
                        if not r['unsolvable'] and r['status'] in ('UNSOLVABLE','SKIPPED')]
        record.update(status='COMPLETED',metrics=report['metrics'],false_refusals=false_refusals,
            truncations=[r['task_id'] for r in report['rows'] if r['status']=='TRUNCATED'],
            rows=report['rows'])
        print(json.dumps(dict(false_refusals=false_refusals,truncations=record['truncations'])))
    except Exception as exc:
        record.update(status='FAILED',error_type=type(exc).__name__)
        raise
    finally:
        control.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Control:',control)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--phase',choices=['offline','noncoding','coding'],required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--profile',choices=['baseline','spacious'],default='baseline')
    p.add_argument('--replay',action='store_true')
    asyncio.run(execute(p.parse_args()))
