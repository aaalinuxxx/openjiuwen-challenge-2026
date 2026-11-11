"""Local credentials, never included in reports. No embedded fallback key."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT.parent / 'neuraldeep.txt'

def load_settings(path=DEFAULT_CONFIG):
    path = Path(path)
    values = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                values[name.strip()] = value.strip().strip('"').strip("'")
    else:
        values = {k: os.environ.get(k, '') for k in ('LLM_BASE_URL', 'LLM_API_KEY')}
    url = values.get('LLM_BASE_URL', '').rstrip('/')
    if url != 'https://api.neuraldeep.ru/v1' or not values.get('LLM_API_KEY'):
        raise ValueError('Valid API settings required in local TXT or environment; values are not logged')
    return dict(LLM_BASE_URL=url, LLM_API_KEY=values['LLM_API_KEY'])
