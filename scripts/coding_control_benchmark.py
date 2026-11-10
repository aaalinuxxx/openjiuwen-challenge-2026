"""Offline structural checks for H05/H11; scripted responses, no model evidence."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.config import TaskContext
from harness.agents.coding_solver import solve_coding_task

class ScriptedBridge:
    def __init__(self, replies): self.replies=list(replies); self.prompts=[]
    async def complete(self, **kwargs):
        self.prompts.append(kwargs['user_prompt'])
        return self.replies.pop(0),0,0,0

def test_code(expression):
    return 'import unittest\nimport mylib\nclass T(unittest.TestCase):\n    def test_value(self):\n        '+expression+'\nif __name__=="__main__": unittest.main()\n'

async def run(label):
    rows=[]
    with tempfile.TemporaryDirectory(prefix='oj-coding-controls-') as tmp:
        for name in ('feedback','all_tests'):
            work=Path(tmp)/name; work.mkdir()
            if name=='feedback':
                original='def f():\n    return 0\n'
                failed='def f():\n    return 1  # PATCH_ONE_MARKER\n'
                corrected='def f():\n    return 2\n'
                (work/'test_a.py').write_text(test_code('self.assertEqual(mylib.f(), 2)'),encoding='utf-8')
                bridge=ScriptedBridge([failed,corrected])
            else:
                original='def f(x):\n    return x\n'
                corrected='def f(x):\n    return abs(x)\n'
                (work/'test_a.py').write_text(test_code('self.assertEqual(mylib.f(2), 2)'),encoding='utf-8')
                (work/'test_b.py').write_text(test_code('self.assertEqual(mylib.f(-2), 2)'),encoding='utf-8')
                bridge=ScriptedBridge([corrected])
            (work/'mylib.py').write_text(original,encoding='utf-8')
            ctx=TaskContext(name,'coding','Fix mylib.py without changing tests.',1,work,work,1000,True)
            result=await solve_coding_task(ctx,bridge)
            row=dict(case=name,status=result.status,scripted_calls=len(bridge.prompts),
                     corrected_source_copied=(work/'mylib.py').read_text(encoding='utf-8').strip()==corrected.strip())
            if name=='feedback':
                row['second_prompt_matches_failed_patch']=len(bridge.prompts)>1 and failed.strip() in bridge.prompts[1]
            else:
                row['all_tests_seen']=bool(bridge.prompts) and 'test_b.py' in bridge.prompts[0]
            rows.append(row)
    result=dict(label=label,api_calls=0,scope='scripted bridge; real unittest subprocesses; no LLM quality/cost inference',rows=rows,
        solver_sha256=hashlib.sha256((ROOT/'harness/agents/coding_solver.py').read_bytes()).hexdigest())
    with (ROOT/'experiments'/f'{label}.json').open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
    print(json.dumps(rows))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--label',required=True); a=p.parse_args()
    if not a.label.replace('_','').isalnum(): p.error('Invalid label')
    asyncio.run(run(a.label))
