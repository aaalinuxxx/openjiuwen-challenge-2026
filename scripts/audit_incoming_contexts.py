"""Offline fixture/context audit; no model calls, expected labels never sent."""
import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.agents.search_solver import _parse_kb
from harness.agents.kb_context import build_kb_context
BASE=ROOT/'experiments/E110_incoming_context'
spec=importlib.util.spec_from_file_location('e110_old_context',BASE/'baseline_kb_context.py');old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
labels=json.loads((BASE/'labels.json').read_text(encoding='utf-8'));details=[]
for name,t in labels.items():
    folder=BASE/'tasks'/name;public=json.loads((folder/'task.json').read_text(encoding='utf-8'))
    assert set(public)=={'task_id','task_type','instruction','reward'}
    kb=_parse_kb(folder/'kb');before=old.build_kb_context(t['instruction'],kb)
    forward=build_kb_context(t['instruction'],kb,include_incoming=False);incoming=build_kb_context(t['instruction'],kb,include_incoming=True)
    assert (before.text,before.names,before.limits,before.complete_kb)==(forward.text,forward.names,forward.limits,forward.complete_kb)
    assert len(incoming.text.encode('utf-8'))<=12000 and len(incoming.names)<=32
    details.append(dict(task_id=name,baseline_exact=True,forward_names=list(forward.names),incoming_names=list(incoming.names),forward_bytes=len(forward.text.encode('utf-8')),incoming_bytes=len(incoming.text.encode('utf-8')),incoming_complete=incoming.complete_kb))
assert len(details)==8
(BASE/'context_audit.json').write_text(json.dumps(dict(passed=True,actual_http_calls=0,cases=details),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(passed=True,cases=len(details))))
