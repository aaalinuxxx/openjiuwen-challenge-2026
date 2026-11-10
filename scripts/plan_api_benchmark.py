"""H04.2 paired pilot: one model, JSON plan versus Python, six CSV tasks.

Default: validate fixtures without credentials/network. --live explicitly runs
at most twelve API calls, no retries. Uses the existing Python subprocess
runner (timeout, not an OS security sandbox). No production routing changes.
"""
import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agents.calculation_plans import sales_plan_from_json, execute_sales_plan
from harness.sandbox.executor import run_python_snippet
from sample_api_benchmark import Bridge, write_json

MODEL = 'qwen3.8-27b-noreason'
OUTPUT_CAP = 200
TABLE = ('product,region,month,units,price,refunded\n'
         'widget,north,2,6,0.10,no\nwidget,south,3,10,0.20,no\n'
         'gadget,north,1,100,0.15,no\nwidget,north,3,14,0.30,yes\n'
         'widget,north,4,50,0.40,no\n')
SYSTEMS = {
    'json': 'Translate the task into ONLY a JSON object with operation (sum/revenue/count/mean/max), '
            'product (string), first_month and last_month (integers 1..12 inclusive), region (string or null). '
            'sum/mean/max aggregate units; revenue sums units*price; count counts rows. '
            'No other fields or operations exist. If ANY requested condition cannot be represented, output ONLY '
            'UNSUPPORTED. Do not omit constraints. No markdown or computed answers.',
    'python': 'Write ONLY raw executable Python 3 code (no markdown fences, no explanations) that reads '
              'data.csv in the current directory and prints ONLY the final numeric answer to stdout. '
              'Use Python standard library only, exact decimal arithmetic where needed. Do not modify files.'}


def cases():
    # Independent reference values: 6+14, .6+2+4.2, 3, (6+14)/2, max(6,10,14), 6+10.
    definitions = [
        ('regional_units', 'For widget orders in the north region during February and March, report total unit volume.', 'sum', 'north', '20'),
        ('proceeds', 'Calculate proceeds (units times price) from widget sales during February and March, across all regions.', 'revenue', None, '6.8'),
        ('record_count', 'Count records, not units, for widget in months 2 and 3 across every region.', 'count', None, '3'),
        ('average', 'For north-region widget rows in months 2 and 3, find average units per row.', 'mean', 'north', '10'),
        ('largest', 'Find the largest units value among widget records dated February or March, regardless of region.', 'max', None, '14'),
        ('refund_constraint', 'Add units for widget in months 2 and 3 across all regions, but exclude rows whose refunded field is yes.', 'sum', None, '16')]
    result = []
    for name, question, operation, region, expected in definitions:
        supported = name != 'refund_constraint'
        plan = dict(operation=operation, product='widget', first_month=2, last_month=3, region=region)
        filters = "r['product']=='widget' and 2<=int(r['month'])<=3"
        if region:
            filters += " and r['region']=='north'"
        if not supported:
            filters += " and r['refunded']!='yes'"
        value = "Decimal(1)" if operation == 'count' else "Decimal(r['units'])"
        if operation == 'revenue':
            value += "*Decimal(r['price'])"
        aggregate = 'max(values)' if operation == 'max' else 'sum(values, Decimal(0))'
        if operation == 'mean':
            aggregate += '/len(values)'
        code = ("import csv\nfrom decimal import Decimal\nwith open('data.csv', newline='') as f:\n"
                f"    values=[{value} for r in csv.DictReader(f) if {filters}]\nprint({aggregate})")
        result.append(dict(id=name, question=question, expected=expected, json_supported=supported,
                           fixture_json=json.dumps(plan) if supported else 'UNSUPPORTED', fixture_python=code))
    return result


def prompt(case, table=TABLE):
    return ('File: data.csv\nHeader & first rows (preview, read the entire file to compute):\n'
            +'\n'.join(table.splitlines()[:4])+'\nTask: '+case['question'])


def evaluate(arm, response, folder):
    if arm == 'json':
        plan = sales_plan_from_json(response)
        return ('UNKNOWN', None) if plan is None else execute_sales_plan(folder/'data.csv', plan)
    ok, stdout, error = run_python_snippet(response, folder)
    if not ok or not stdout.strip():
        return 'EXECUTION_FAILED', None
    return 'SOLVED', stdout.strip().splitlines()[-1].strip()


def is_correct(status, answer, expected):
    if status != 'SOLVED' or answer is None:
        return False
    try:
        value = Decimal(answer)
        return value.is_finite() and value == Decimal(expected)
    except InvalidOperation:
        return False


def settings_from(path):
    settings = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            settings[key.strip()] = value.strip().strip('"').strip("'")
    settings['LLM_BASE_URL'] = settings.get('LLM_BASE_URL', '').rstrip('/')
    if settings['LLM_BASE_URL'] != 'https://api.neuraldeep.ru/v1' or not settings.get('LLM_API_KEY', '').startswith('sk-'):
        raise ValueError('Check API configuration; values are not logged')
    return settings


def paired_summary(rows):
    # Invalid JSON or failed execution is a measured failure, not a reason to
    # remove the pair. Only missing API responses make a pair incomplete.
    ids = {r['task_id'] for r in rows}
    completed = sorted(task for task in ids if
                       {r['arm'] for r in rows if r['task_id'] == task and isinstance(r.get('response'), str)}
                       == set(SYSTEMS))
    return dict(task_ids=completed, complete_pairs=len(completed),
                arms={arm: dict(attempted=sum(r['arm']==arm and r['task_id'] in completed for r in rows),
                                 correct=sum(r['arm']==arm and r['task_id'] in completed and r['correct'] for r in rows),
                                 effective_tokens=round(sum(r['effective_cost'] for r in rows if r['arm']==arm and r['task_id'] in completed), 3))
                      for arm in SYSTEMS})


async def run(args):
    if args.suite == 'constraints':
        from plan_constraint_cases import TABLE as table, cases as constraint_cases
        specs, experiment = constraint_cases(), 'E22'
    else:
        specs, table, experiment = cases(), TABLE, 'E19'
    settings = settings_from(args.config) if args.live else {}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/(experiment+'_plan_pairs_'+('live_' if args.live else 'fixtures_')+stamp)
    directory.mkdir(parents=True)
    output = directory/'report.json'
    sources = list((ROOT/'harness').rglob('*.py'))+[Path(__file__), ROOT/'scripts/sample_api_benchmark.py', ROOT/'scripts/plan_constraint_cases.py']
    report = dict(mode='LIVE_PILOT' if args.live else 'FIXTURE_CHECK_ONLY', model=MODEL, output_cap=OUTPUT_CAP,
                  scope='six synthetic dev tasks; direct fallback comparison; not a holdout or full harness', suite=args.suite,
                  metric='exact numeric value; UNKNOWN is not a solution', local_budget=args.budget,
                  requests=[], rows=[], effective_tokens=0, has_unaccounted_request=False,
                  dataset_sha256=hashlib.sha256(json.dumps(dict(specs=specs, table=table), sort_keys=True).encode()).hexdigest(),
                  source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                  cases=specs, systems=SYSTEMS, table=table)
    bridge = Bridge(settings, args.budget, output, report, max_calls=12)
    write_json(output, report)
    with tempfile.TemporaryDirectory(prefix='oj-plan-pairs-') as tmp:
        for index, case in enumerate(specs):
            order = ('json', 'python') if index % 2 == 0 else ('python', 'json')
            user = prompt(case, table)
            pair_reserve = sum(Bridge.request_reserve(SYSTEMS[arm], user, OUTPUT_CAP) for arm in order)
            if args.live and (bridge.blocked or bridge.spent+pair_reserve > args.budget):
                report['stop_reason'] = 'STOP_BEFORE_PAIR: request error or insufficient heuristic reserve'
                break
            for arm in order:
                folder = Path(tmp)/case['id']/arm
                folder.mkdir(parents=True)
                (folder/'data.csv').write_text(table, encoding='utf-8')
                before = bridge.spent
                row = dict(task_id=case['id'], arm=arm, order_in_pair=order.index(arm),
                           json_supported=case['json_supported'], correct=False)
                bridge.task_id = case['id']+':'+arm
                try:
                    if args.live:
                        response, *_ = await bridge.complete(MODEL, SYSTEMS[arm], user, OUTPUT_CAP, temperature=0)
                    else:
                        response = case['fixture_'+arm]
                    # Save the original model output before executing/interpreting it.
                    row['response'] = response
                    report['rows'].append(row)
                    write_json(output, report)
                    status, answer = evaluate(arm, response, folder)
                    if (folder/'data.csv').read_text(encoding='utf-8') != table:
                        status, answer = 'INPUT_MODIFIED', None
                    row.update(status=status, answer=answer, correct=is_correct(status, answer, case['expected']))
                    if not args.live:
                        row['fixture_pass'] = row['correct'] or (arm == 'json' and not case['json_supported'] and status == 'UNKNOWN')
                except Exception as exc:
                    row.update(status='INTERPRETATION_FAILED' if 'response' in row else 'ERROR_OR_LOCAL_STOP',
                               error_type=type(exc).__name__)
                    if not any(r is row for r in report['rows']):
                        report['rows'].append(row)
                row['effective_cost'] = round(bridge.spent-before, 3)
                write_json(output, report)
                print(json.dumps({k:v for k,v in row.items() if k != 'response'}), flush=True)
                if bridge.blocked:
                    break
            if bridge.blocked:
                break
    if args.live:
        # Cost totals include accounted errors; unresolved requests remain explicit.
        report['summary'] = dict(calls=bridge.calls, effective_tokens=round(bridge.spent, 3),
            has_unaccounted_request=report['has_unaccounted_request'],
            arms={arm: dict(attempted=sum(r['arm']==arm for r in report['rows']),
                            correct=sum(r['arm']==arm and r['correct'] for r in report['rows']),
                            supported_correct=sum(r['arm']==arm and r['json_supported'] and r['correct'] for r in report['rows']),
                            effective_tokens=round(sum(r['effective_cost'] for r in report['rows'] if r['arm']==arm), 3))
                  for arm in SYSTEMS},
            paired=paired_summary(report['rows']),
            planned_pairs=len(specs))
    else:
        report['summary'] = dict(fixture_checks=len(report['rows']),
                               fixture_passes=sum(r.get('fixture_pass', False) for r in report['rows']),
                               api_calls=0, model_quality_measured=False)
    write_json(output, report)
    print(json.dumps(report['summary']))
    print('Report:', output)
    if not args.live and report['summary']['fixture_passes'] != 12:
        raise SystemExit('Fixture checks failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--suite', choices=('pilot', 'constraints'), default='pilot')
    parser.add_argument('--budget', type=float, default=3000)
    parser.add_argument('--config', type=Path, default=ROOT.parent/'neuraldeep.txt')
    args = parser.parse_args()
    if not math.isfinite(args.budget) or not 0 <= args.budget <= 3000:
        parser.error('Budget must be between 0 and 3000')
    asyncio.run(run(args))
