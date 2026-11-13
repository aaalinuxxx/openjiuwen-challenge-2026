"""Freeze targeted inverse-search tasks and independent small authored controls."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'experiments/E110_incoming_context'
labels=json.loads((ROOT/'experiments/E105_ranking_validation/labels.json').read_text(encoding='utf-8'))
old=['validate_086_fresh_search_inverse','validate_095_fresh_search_custodian','validate_075_fresh_search_latest','validate_056_fresh_search_conflict','validate_019_search_three_hop']
out={}
for name in old:
    t=dict(labels[name]);t['group']='E110_observed_inverse' if name==old[0] else 'E110_control'
    shutil.copytree(ROOT/'experiments/E105_ranking_validation/tasks'/name,DEST/'tasks'/name)
    out[name]=t
new=[dict(task_id='incoming_employer',instruction='Use only kb/. Which person has employer Cedar Works? Exactly one person matches. Return only the exact person name to answer.txt.',expected='Mira Holt',unsolvable=False,files={'a.md':'# Cedar Works\nheadquarters: Bern\n','b.md':'# Mira Holt\nemployer: Cedar Works\n','c.md':'# Oren Vale\nemployer: Different Company\n'}),
 dict(task_id='incoming_then_outgoing',instruction='Use only kb/. What is the headquarters city of the employer of the person whose tutor is Ivo Reed? Exactly one person has that tutor. Return only the exact city to answer.txt.',expected='Porto',unsolvable=False,files={'a.md':'# Ivo Reed\nborn: 1981\n','b.md':'# Tess Dale\ntutor: Ivo Reed\nemployer: Silver Loom\n','c.md':'# Silver Loom\nheadquarters: Porto\n','d.md':'# Uma Pike\ntutor: Other Person\n'}),
 dict(task_id='incoming_ambiguous',instruction='Use only kb/. Give the unique name of the person whose tutor is Aron Glen. Return UNSOLVABLE if no unique name follows from the records. Write the answer to answer.txt.',expected='UNSOLVABLE',unsolvable=True,files={'a.md':'# Aron Glen\nborn: 1970\n','b.md':'# Lena Moss\ntutor: Aron Glen\n','c.md':'# Rina Ash\ntutor: Aron Glen\n'})]
for task in new:
    files=task.pop('files');task.update(task_type='search',reward=1,group='E110_new_authored')
    folder=DEST/'tasks'/task['task_id'];(folder/'kb').mkdir(parents=True)
    for name,content in files.items():(folder/'kb'/name).write_text(content,encoding='utf-8',newline='')
    (folder/'task.json').write_text(json.dumps({k:task[k] for k in ('task_id','task_type','instruction','reward')},indent=2)+'\n',encoding='utf-8',newline='')
    out[task['task_id']]=task
(DEST/'labels.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='')
print(json.dumps(dict(total=len(out),solvable=sum(not t['unsolvable'] for t in out.values()))))
