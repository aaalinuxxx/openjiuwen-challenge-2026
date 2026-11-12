"""Read-only root-cause probes for failures observed in E107. Zero HTTP."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.agents.search_solver import _parse_kb
from harness.agents.kb_context import build_kb_context
from harness.agents.coding_target import select_coding_target
BASE=ROOT/'experiments/E105_ranking_validation/new_tasks'
latest=_parse_kb(BASE/'fresh_search_latest/kb')
assert 'mistral' in latest['Product launches'] and 'Mistral' not in latest['Product launches']
original=(BASE/'fresh_search_latest/kb/products.md').read_text(encoding='utf-8')
assert 'Mistral' in original
inv_meta=json.loads((BASE/'fresh_search_inverse/task.json').read_text(encoding='utf-8'))
inv_entities=_parse_kb(BASE/'fresh_search_inverse/kb');context=build_kb_context(inv_meta['instruction'],inv_entities)
assert 'Nora Pine' in inv_entities and 'Nora Pine' not in context.names
assert inv_entities['Nora Pine']['tutor']=='Lina Vale'
coding=[]
for name in ('fresh_coding_unique','fresh_coding_rotate','fresh_coding_transpose'):
    task=BASE/name;instruction=json.loads((task/'task.json').read_text(encoding='utf-8'))['instruction']
    files=[p for p in task.glob('*.py') if not p.name.startswith('test_')]
    actual=select_coding_target(instruction,files)
    diagnostic=re.sub(r'(?i)do not modify (?:values|input|matrix)\.', '',instruction)
    relaxed=select_coding_target(diagnostic,files)
    assert actual is None and relaxed is not None and relaxed.name=='mylib.py'
    coding.append(dict(task=name,original_target=None,diagnostic_without_nonmutation_clause=relaxed.name,note='Diagnostic only: removing the instruction is NOT a proposed production fix. Preserve nonmutation requirement when fixing parser.'))
out=dict(mode='OFFLINE_READ_ONLY_DIAGNOSTIC',actual_http_calls=0,checks_passed=True,findings=dict(property_case_loss=dict(original='Mistral',serialized='mistral',cause='All KB property names are lowercased, including product names used as keys.'),inverse_relation=dict(selected=list(context.names),excluded_answer='Nora Pine',cause='Traversal only follows outgoing relation values from mentioned entities.'),coding_nonmutation_confusion=coding),production_changed=False)
(ROOT/'experiments/E107_failure_diagnostics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out))
