"""Execute the predeclared schedule sequentially, stopping on any failed audit."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'experiments/E130_score_selection'
def main():
    design=json.loads((BASE/'design.json').read_text())
    for name in design['schedule']:
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/score_selection_benchmark.py'),'--plan',str(BASE/('plan_'+name+'.json')),'--live'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        (BASE/('process_'+name+'.json')).write_text(json.dumps(dict(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr),indent=2)+'\n')
        print(name,proc.returncode,flush=True)
        if proc.returncode:print(proc.stderr[-1000:],flush=True);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
