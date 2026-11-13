"""Read-only comparison of integrated ordering and frozen experiment ordering."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from run_agent import parse_args,build_config
from harness.planner.scheduler import TaskScheduler
from harness.planner.ranking_calibration import MEDIAN_ORDERING_COSTS
BASE=ROOT/'experiments/E116_production_ranking'
cal=json.loads((ROOT/'experiments/E103_calibrated_ranking/calibration.json').read_text(encoding='utf-8'))
assert dict(MEDIAN_ORDERING_COSTS)==cal['median_costs']
refs={"roi":"experiments/E115_roi_baseline_offline_20261113T073507147902/ranking.json","calibrated":"experiments/E115_calibrated_baseline_offline_20261113T073507160423/ranking.json"}
checks={}
for policy in ('roi','calibrated'):
    args=parse_args(['--tasks-dir',str(ROOT/'experiments/E105_ranking_validation/tasks'),'--budget','500','--max-api-calls','30','--ranking-policy',policy])
    config=build_config(args,settings={});config.execution_engine='direct'
    rows=TaskScheduler(config).discover_and_rank_tasks()
    actual=[{k:r[k] for k in ('task_id','roi','expected_cost','reward')} for r in rows]
    expected=json.loads((ROOT/refs[policy]).read_text(encoding='utf-8'))
    if actual!=expected:
        print(json.dumps(dict(policy=policy,actual_count=len(actual),expected_count=len(expected),first_differences=[dict(index=i,actual=a,expected=e) for i,(a,e) in enumerate(zip(actual,expected)) if a!=e][:5])))
    assert actual==expected
    checks[policy]=dict(identical=True,ranked_tasks=len(rows))
default=build_config(parse_args(['--tasks-dir','.']),settings={})
explicit=build_config(parse_args(['--tasks-dir','.','--ranking-policy','calibrated']),settings={})
assert default==explicit
(BASE/'equivalence.json').write_text(json.dumps(dict(passed=True,actual_http_calls=0,ranking=checks,default_equals_explicit=True),indent=2)+'\n',encoding='utf-8')
print(json.dumps(checks))
