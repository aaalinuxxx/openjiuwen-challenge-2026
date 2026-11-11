"""Matched reasoning/noreason probe. Requires --live; saves bounded raw responses."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api_settings import DEFAULT_CONFIG, load_settings
from harness.agents.base_harness import RobustHTTPTransport, parse_usage
from harness.planner.budget_tracker import BudgetTracker, BudgetDenied

CASES = [('precedence', 'Solve: 2 + 2 * 2. Output ONLY the single final number.', '6'),
         ('multiply', 'Compute 17 * 19. Output ONLY the single final number.', '323')]
MODELS = ('qwen3.8-27b-noreason', 'qwen3.8-27b')
CAP = 128


async def run(args):
    if not args.live:
        print('No API calls. Use --live --budget 800 for four matched requests.')
        return
    settings = load_settings(args.config)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = ROOT/'experiments'/f'E36_reasoning_pairs_{stamp}'
    directory.mkdir(parents=True, exist_ok=False)
    tracker = BudgetTracker(args.budget, directory/'budget.json', max_requests=4)
    report = dict(mode='LIVE_MATCHED_PILOT', candidate_reasoning_contract='included',
        contract_status='candidate, limited evidence; not universal provider guarantee',
        max_calls=4, output_cap=CAP, requests=[], source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    path = directory/'report.json'
    def save():
        report['budget'] = tracker.snapshot()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    sender = RobustHTTPTransport(settings['LLM_BASE_URL'], settings['LLM_API_KEY'])
    for index, (case_id, question, expected) in enumerate(CASES):
        models = MODELS if index % 2 == 0 else MODELS[::-1]
        for model in models:
            estimate = len(question.encode('utf-8')) + 1024
            try:
                ticket, cap = await tracker.reserve(case_id+':'+model, args.budget, estimate, CAP)
            except BudgetDenied:
                report['stop_reason'] = 'Local gate closed'
                save()
                break
            row = dict(case_id=case_id, model=model, question=question, expected=expected,
                       output_cap=cap, status='STARTED')
            report['requests'].append(row)
            save()
            payload = dict(model=model, messages=[dict(role='user', content=question)],
                           max_tokens=cap, temperature=0)
            try:
                data = await sender.send(payload)
                # Candidate mode is explicit for this experiment only, never silently
                # enabled for the production harness.
                counts = parse_usage(data, 'included')
                await tracker.settle(ticket, *counts)
                row.update(status='ACCOUNTED', usage=data['usage'], effective_cost=counts[0]/10+counts[1]+counts[2])
                save()
                choice = data['choices'][0]
                message = choice['message']
                row.update(content=message.get('content'), reasoning_content=message.get('reasoning_content'),
                           finish_reason=choice.get('finish_reason'))
                row['correct'] = (str(row['content']).strip() == expected and row['finish_reason'] != 'length')
                usage = row['usage']
                row['total_equals_prompt_plus_completion'] = usage.get('total_tokens') == usage['prompt_tokens']+usage['completion_tokens']
            except Exception as exc:
                await tracker.unknown(ticket, type(exc).__name__)
                row['error_type'] = type(exc).__name__
                row['status'] = tracker.events[ticket]['status']
                report['stop_reason'] = 'Response or transport error; no retries'
                save()
                print(json.dumps(dict(status=row['status'], error_type=row['error_type'])))
                break
            save()
            print(json.dumps({k:row.get(k) for k in ('case_id','model','status','correct','effective_cost','finish_reason')}))
        if tracker.proxy_exhausted or 'stop_reason' in report:
            break
    matched = [case_id for case_id,_,_ in CASES if sum(r['case_id']==case_id and r.get('status')=='ACCOUNTED'
               and r.get('finish_reason') not in (None,'length') for r in report['requests']) == 2]
    report['summary'] = dict(complete_pairs=len(matched), requests=len(report['requests']),
        known_effective_tokens=tracker.spent_effective_tokens,
        has_unaccounted_request=tracker.has_unaccounted_request,
        models={m:dict(correct=sum(bool(r.get('correct')) for r in report['requests'] if r['model']==m),
                       known_cost=sum(r.get('effective_cost',0) for r in report['requests'] if r['model']==m))
                for m in MODELS})
    save()
    print(json.dumps(report['summary']))
    print('Report:', path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--budget', type=float, default=0)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    if not math.isfinite(args.budget) or not 0 <= args.budget <= 1500 or (args.live and args.budget <= 0):
        parser.error('A live pilot requires an explicit budget between 0 and 1500')
    asyncio.run(run(args))
