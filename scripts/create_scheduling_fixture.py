"""H04.23: 100-task workload with independent random rewards, repeated known families."""
import json,random,shutil
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'experiments/E77_mixed_integration'
TARGET=ROOT/'experiments/E95_scheduling'

def main():
    if TARGET.exists():raise ValueError('Refuse overwrite')
    original=json.loads((SOURCE/'labels.json').read_text(encoding='utf-8'))
    rng=random.Random(2026111201)
    ids=sorted(original)
    pool=ids*3+rng.sample(ids,7)
    rng.shuffle(pool)
    labels={};lineage=[]
    for i,source_id in enumerate(pool):
        task_id=f'load_{i:03d}_{source_id}';reward=rng.randint(1,5)
        target=TARGET/'tasks'/task_id
        shutil.copytree(SOURCE/'tasks'/source_id,target)
        truth=dict(original[source_id],task_id=task_id,reward=reward,source_task_id=source_id)
        labels[task_id]=truth
        public={k:truth[k] for k in ('task_id','task_type','instruction','reward')}
        (target/'task.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lineage.append(dict(task_id=task_id,source_task_id=source_id,reward=reward))
    (TARGET/'labels.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validation=dict(seed=2026111201,count=len(labels),unique_source_families=len(set(pool)),solvable=sum(not t['unsolvable'] for t in labels.values()),max_score=sum(t['reward'] for t in labels.values() if not t['unsolvable']),by_type=dict(Counter(t['task_type'] for t in labels.values())),reward_counts=dict(Counter(t['reward'] for t in labels.values())),lineage=lineage)
    assert len(labels)==100
    (TARGET/'fixture_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in validation.items() if k!='lineage'}))
if __name__=='__main__':main()
