"""Replay completed paired API responses; spends no tokens, never executes code.

The gate was designed after E19. Replay on E19 is exploratory/in-sample and
cannot establish its accuracy or savings on new questions.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agents.plan_scope import json_plan_risks
from plan_api_benchmark import is_correct


def replay(report):
    if report.get('mode') != 'LIVE_PILOT' or report.get('has_unaccounted_request'):
        raise ValueError('Requires an accounted live paired report')
    columns = next(csv.reader(io.StringIO(report['table'])))
    lookup = {(row['task_id'], row['arm']): row for row in report['rows']}
    if len(lookup) != len(report['rows']):
        raise ValueError('Duplicate task/arm')
    totals, traces = {}, []
    for policy in ('python_only', 'json_only', 'json_then_python_on_failure', 'risk_gate_then_cascade'):
        rows = []
        for case in report['cases']:
            if any((case['id'], arm) not in lookup or not isinstance(lookup[case['id'], arm].get('response'), str)
                   for arm in ('json', 'python')):
                continue
            # Routing has access to question/schema/status, never the oracle or
            # the json_supported annotation. Oracle is used only after routing.
            risks = json_plan_risks(case['question'], columns)
            selected = ['python'] if policy == 'python_only' or (policy == 'risk_gate_then_cascade' and risks) else ['json']
            if selected == ['json'] and policy in ('json_then_python_on_failure', 'risk_gate_then_cascade'):
                if lookup[case['id'], 'json']['status'] != 'SOLVED':
                    selected.append('python')
            last = lookup[case['id'], selected[-1]]
            row = dict(policy=policy, task_id=case['id'], selected_arms=selected, risk_signals=risks,
                       answer=last.get('answer'), correct=is_correct(last['status'], last.get('answer'), case['expected']),
                       replay_effective_tokens=round(sum(lookup[case['id'], arm]['effective_cost'] for arm in selected), 3),
                       replay_calls=len(selected))
            rows.append(row)
        traces.extend(rows)
        totals[policy] = dict(tasks=len(rows), correct=sum(r['correct'] for r in rows),
                              replay_effective_tokens=round(sum(r['replay_effective_tokens'] for r in rows), 3),
                              replay_calls=sum(r['replay_calls'] for r in rows))
    return totals, traces


def main(args):
    source = args.report.read_bytes()
    report = json.loads(source)
    totals, rows = replay(report)
    result = dict(mode='OFFLINE_POLICY_REPLAY', new_api_calls=0,
                  limitation='gate designed after E19; exploratory replay, not a new live cascade measurement',
                  source_report=str(args.report.resolve()), source_sha256=hashlib.sha256(source).hexdigest(),
                  source_dataset_sha256=report['dataset_sha256'], summary=totals, rows=rows,
                  gate_sha256=hashlib.sha256((ROOT/'harness/agents/plan_scope.py').read_bytes()).hexdigest())
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    output = ROOT/'experiments'/('E21_plan_policy_replay_'+stamp+'.json')
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(totals))
    print('Report:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    main(parser.parse_args())
