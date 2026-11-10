"""One bounded API diagnostic, standard library only; never logs credentials."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT.parent / 'neuraldeep.txt')
    parser.add_argument('--generate', action='store_true', help='One noreason request, max_tokens=16, no retries')
    args = parser.parse_args()
    settings = {}
    try:
        for line in args.config.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                settings[k.strip()] = v.strip().strip('\"').strip("'")
    except OSError:
        parser.error('Cannot read configuration file')
    if settings.get('LLM_BASE_URL', '').rstrip('/') != 'https://api.neuraldeep.ru/v1':
        parser.error('Expected API endpoint https://api.neuraldeep.ru/v1')
    if not settings.get('LLM_API_KEY'):
        parser.error('LLM_API_KEY is missing')
    payload = dict(model='qwen3.8-27b-noreason',
                   messages=[dict(role='user', content='Reply only OK.')],
                   max_tokens=16, temperature=0)
    suffix = '/chat/completions' if args.generate else '/models'
    request = urllib.request.Request(settings['LLM_BASE_URL'].rstrip('/') + suffix,
        data=json.dumps(payload).encode() if args.generate else None,
        headers={'Authorization': 'Bearer ' + settings['LLM_API_KEY'],
                 'Content-Type': 'application/json'})
    report = dict(at=datetime.now(timezone.utc).isoformat(),
                  mode='single_generation' if args.generate else 'list_models',
                  requested_output_cap=16 if args.generate else 0,
                  retries=0, status='STARTED')
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            data = json.load(response)
            report.update(status='OK', http_status=response.status)
        if args.generate:
            usage = data.get('usage') or {}
            report['usage'] = {k: v for k, v in usage.items()
                               if k in ('prompt_tokens', 'completion_tokens', 'total_tokens',
                                        'reasoning_tokens', 'completion_tokens_details',
                                        'prompt_tokens_details')}
            answer = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            report['answer_is_OK'] = str(answer).strip() == 'OK'
            # Preserve usage for inspection; reasoning billing semantics not guessed.
        else:
            report['allowed_models_available'] = [m.get('id') for m in data.get('data', [])
                if m.get('id') in ('qwen3.8-27b', 'qwen3.8-27b-noreason',
                                   'qwen3.6-35b-a3b', 'qwen3.6-35b-a3b-noreason')]
    except urllib.error.HTTPError as exc:
        report.update(status='HTTP_ERROR', http_status=exc.code)
    except Exception as exc:
        report.update(status='CONNECTION_OR_RESPONSE_ERROR', error_type=type(exc).__name__)
    output = ROOT / 'experiments'
    output.mkdir(exist_ok=True)
    target = output / ('api_probe_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Report:', target)
    return 0 if report['status'] == 'OK' else 1


if __name__ == '__main__':
    raise SystemExit(main())
