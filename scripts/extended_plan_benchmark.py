"""H04.7: six v2 JSON requests, reusing accounted E22 Python/v1 baselines.

Default is offline fixtures. --live spends tokens on v2 only. This is a
sequential comparison on known dev cases, not a fresh randomized paired trial.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agents.extended_plans import extended_plan_from_json, execute_extended_plan
from plan_api_benchmark import MODEL, OUTPUT_CAP, is_correct, prompt, settings_from
from plan_constraint_cases import TABLE, cases
from sample_api_benchmark import Bridge, write_json

SYSTEM = (
    'Translate the task into ONLY a JSON object: operation (sum/revenue/count/mean/max/median), '
    'product (string), months (array of distinct integers 1..12; include ONLY requested months), '
    'region (string or null; optional), predicates (array; optional). '
    'sum/mean/max/median aggregate units; revenue sums units*price; count counts rows. '
    'Each predicate is {"column":existing CSV column,"op":eq/ne/gt/ge/lt/le,"value":string}. '
    'eq/ne compare exact text; gt/ge/lt/le compare decimal numbers. ALL predicates apply together. '
    'Preserve EVERY condition. If any condition is not representable, output ONLY UNSUPPORTED. '
    'No markdown or computed answers.')


def fixture(case_id):
    plan = dict(operation='sum', product='widget', months=[2, 3])
    if case_id == 'count_control': plan['operation'] = 'count'
    elif case_id == 'refund_alias': plan['predicates'] = [dict(column='refunded', op='eq', value='no')]
    elif case_id == 'price_threshold': plan['predicates'] = [dict(column='price', op='ge', value='0.20')]
    elif case_id == 'median_units': plan['operation'] = 'median'
    elif case_id == 'separated_months': plan['months'] = [2, 4]
    elif case_id != 'total_control': raise ValueError('Unknown fixture')
    return json.dumps(plan)


def baseline_from(path):
    source = path.read_bytes()
    report = json.loads(source)
    expected_hash = hashlib.sha256(json.dumps(dict(specs=cases(), table=TABLE), sort_keys=True).encode()).hexdigest()
    if (report.get('mode') != 'LIVE_PILOT' or report.get('has_unaccounted_request')
        or report.get('dataset_sha256') != expected_hash or report.get('model') != MODEL
        or report.get('output_cap') != OUTPUT_CAP):
        raise ValueError('Requires an accounted E22 live report with the frozen dataset/model/cap')
    index = {(r['task_id'], r['arm']): r for r in report['rows']}
    if len(index) != 12 or len(report['rows']) != 12 or any(not isinstance(r.get('response'), str) for r in report['rows']):
        raise ValueError('Baseline must contain all six completed pairs')
    return report, index, hashlib.sha256(source).hexdigest()


async def run(args):
    baseline_path = args.baseline
    if baseline_path is None:
        candidates = sorted((ROOT/'experiments').glob('E22_plan_pairs_live_*/report.json'))
        if not candidates: raise ValueError('Run the E22 live benchmark first, or supply --baseline')
        baseline_path = candidates[-1]
    baseline, index, source_hash = baseline_from(baseline_path)
    settings = settings_from(args.config) if args.live else {}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/('E23_extended_plan_'+('live_' if args.live else 'fixtures_')+stamp)
    directory.mkdir(parents=True)
    output = directory/'report.json'
    sources = [Path(__file__), ROOT/'scripts/plan_api_benchmark.py', ROOT/'scripts/plan_constraint_cases.py',
               ROOT/'scripts/sample_api_benchmark.py', ROOT/'harness/agents/extended_plans.py',
               ROOT/'harness/agents/calculation_plans.py']
    report = dict(mode='V2_LIVE' if args.live else 'FIXTURE_CHECK_ONLY',
                  scope='known E22 dev; fresh v2 vs historical v1/Python; not independent holdout',
                  baseline_report=str(baseline_path.resolve()), baseline_sha256=source_hash,
                  dataset_sha256=baseline['dataset_sha256'], model=MODEL, output_cap=OUTPUT_CAP,
                  system=SYSTEM, local_budget=args.budget, requests=[], rows=[], effective_tokens=0,
                  has_unaccounted_request=False,
                  source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    bridge = Bridge(settings, args.budget, output, report, max_calls=6)
    write_json(output, report)
    print('Baseline:', baseline_path)
    with tempfile.TemporaryDirectory(prefix='oj-extended-plan-') as tmp:
        folder = Path(tmp)
        path = folder/'data.csv'
        path.write_text(TABLE, encoding='utf-8')
        for case in cases():
            user = prompt(case, TABLE)
            if args.live and (bridge.blocked or bridge.spent+Bridge.request_reserve(SYSTEM, user, OUTPUT_CAP) > args.budget):
                report['stop_reason'] = 'Error or insufficient request reserve'
                break
            bridge.task_id = case['id']+':json_v2'
            before = bridge.spent
            row = dict(task_id=case['id'], correct=False)
            report['rows'].append(row)
            try:
                if args.live:
                    response, *_ = await bridge.complete(MODEL, SYSTEM, user, OUTPUT_CAP, temperature=0)
                else:
                    response = fixture(case['id'])
                row['response'] = response
                write_json(output, report)
                plan = extended_plan_from_json(response)
                status, answer = ('UNKNOWN', None) if plan is None else execute_extended_plan(path, plan)
                row.update(status=status, answer=answer, correct=is_correct(status, answer, case['expected']))
            except Exception as exc:
                row.update(status='INTERPRETATION_FAILED' if 'response' in row else 'ERROR_OR_LOCAL_STOP',
                           error_type=type(exc).__name__)
            row['effective_cost'] = round(bridge.spent-before, 3)
            write_json(output, report)
            print(json.dumps({k:v for k,v in row.items() if k!='response'}), flush=True)
            if bridge.blocked: break
    if args.live:
        # Count invalid plans as failures; exclude only requests without a response
        # from matched comparisons. Overall spend includes every accounted call.
        matched = [r for r in report['rows'] if isinstance(r.get('response'), str)]
        expected = {c['id']:c['expected'] for c in cases()}
        report['summary'] = dict(calls=bridge.calls, effective_tokens=round(bridge.spent,3),
            has_unaccounted_request=report['has_unaccounted_request'], matched_tasks=len(matched), planned_tasks=6,
            json_v2=dict(correct=sum(r['correct'] for r in matched),
                         effective_tokens=round(sum(r['effective_cost'] for r in matched),3)),
            historical={arm:dict(correct=sum(is_correct(index[r['task_id'],arm]['status'],
                                                       index[r['task_id'],arm].get('answer'), expected[r['task_id']]) for r in matched),
                                  effective_tokens=round(sum(index[r['task_id'],arm]['effective_cost'] for r in matched),3))
                        for arm in ('json','python')})
    else:
        report['summary'] = dict(fixture_checks=len(report['rows']), fixture_passes=sum(r['correct'] for r in report['rows']),
                               api_calls=0, model_quality_measured=False)
    write_json(output, report)
    print(json.dumps(report['summary']))
    print('Report:', output)
    if not args.live and report['summary']['fixture_passes'] != 6:
        raise SystemExit('Fixture checks failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--budget', type=float, default=2000)
    parser.add_argument('--config', type=Path, default=ROOT.parent/'neuraldeep.txt')
    args = parser.parse_args()
    if not math.isfinite(args.budget) or not 0 <= args.budget <= 3000:
        parser.error('Budget must be between 0 and 3000')
    asyncio.run(run(args))
