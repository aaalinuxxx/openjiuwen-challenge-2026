"""Submission-source acceptance without Docker: isolated actual CLI and installed dependency graph."""
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,tempfile
from importlib import metadata
from pathlib import Path
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def runtime_files():
    return sorted([ROOT/'run_agent.py',ROOT/'requirements.txt']+[p for p in (ROOT/'harness').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')])
def dependencies():
    pending=['openjiuwen==0.1.19','httpx>=0.28.1,<0.29'];seen=set();rows=[];errors=[]
    while pending:
        text=pending.pop();req=Requirement(text)
        if req.marker and not req.marker.evaluate({'extra':''}):continue
        name=req.name.lower().replace('_','-')
        try:dist=metadata.distribution(req.name);version=dist.version
        except metadata.PackageNotFoundError:errors.append({'requirement':text,'error':'missing'});continue
        if req.specifier and version not in req.specifier:errors.append({'requirement':text,'installed':version})
        if name in seen:continue
        seen.add(name);requires_python=dist.metadata.get('Requires-Python','')
        if requires_python and platform.python_version() not in SpecifierSet(requires_python):errors.append({'package':name,'requires_python':requires_python})
        rows.append({'name':name,'version':version,'requires_python':requires_python})
        pending.extend(dist.requires or [])
    return {'passed':not errors,'errors':errors,'packages':sorted(rows,key=lambda r:r['name']), 'method':'importlib.metadata + packaging, mandatory dependencies for this platform; pip is absent in this host environment'}
def add_task(tasks,name,kind,instruction,files,workspace=False):
    root=tasks/name;root.mkdir();work=root/'workspace' if workspace else root;work.mkdir(exist_ok=True)
    (root/'task.json').write_text(json.dumps(dict(task_id=name,task_type=kind,instruction=instruction,reward=1)),encoding='utf-8')
    for name,content in files.items():
        f=work/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(content,encoding='utf-8')
    return root,work

def run_cli(app,base,mode):
    root=base/mode;tasks=root/'tasks';tasks.mkdir(parents=True);tmp=root/'tmp';tmp.mkdir();output=root/'solutions.json'
    math='A warehouse starts with 100 boxes. It ships 3 boxes per day for 4 days. How many boxes does it have at the end? Write only the final answer to answer.txt.'
    roots={}
    roots['math_local']=add_task(tasks,'math_local','math',math,{},workspace=True)
    roots['search_local']=add_task(tasks,'search_local','search','In which year was Alba born? Write only the final answer to answer.txt.',{'kb/alba.md':'# Alba\nborn: 1987\n'},workspace=True)
    roots['csv_local']=add_task(tasks,'csv_local','data_analysis',"How many units of product 'widget' were sold in months 5 through 6 inclusive? Write only the final answer to answer.txt.",{'sales.csv':'product,month,units\nwidget,5,4\nwidget,6,5\nwidget,7,80\n'})
    roots['coding_local']=add_task(tasks,'coding_local','coding','Run the tests, preserve code if they pass, then write DONE to answer.txt.',{'mylib.py':'def f(x):\n    return x+1\n','test_mylib.py':'import unittest\nfrom mylib import f\nclass T(unittest.TestCase):\n    def test_f(self):self.assertEqual(f(4),5)\nif __name__=="__main__":unittest.main()\n'},workspace=True)
    roots['missing_data']=add_task(tasks,'missing_data','data_analysis','Read absent.csv and sum qty. Do not invent unavailable input.',{})
    expected={'math_local':'88','search_local':'1987','csv_local':'9','coding_local':'DONE'}
    before={p.relative_to(tasks).as_posix():digest(p) for p in tasks.rglob('*') if p.is_file()}
    env=dict(os.environ);env.setdefault('USERPROFILE',r'C:\Users\PC')
    for name in ('BUDGET','TOKEN_BUDGET','TASKS','OUT','PYTHONPATH'):env.pop(name,None)
    env.update(LLM_BASE_URL='https://fixture.invalid/v1',LLM_API_KEY='offline-fixture',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp))
    command=[sys.executable,str(app/'run_agent.py')]
    if mode=='cli_overrides':
        env.update(BUDGET='150000',TOKEN_BUDGET='140000',TASKS=str(root/'wrong_tasks'),OUT=str(root/'wrong_out.json'))
        command+=['--tasks-dir',str(tasks),'--out-file',str(output),'--budget','0']
    elif mode=='budget_environment':env.update(BUDGET='0',TOKEN_BUDGET='150000',TASKS=str(tasks),OUT=str(output))
    else:env.update(TOKEN_BUDGET='0',TASKS=str(tasks),OUT=str(output))
    process=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90)
    answers={};checks={'exit_zero':process.returncode==0}
    for name,(task,work) in roots.items():
        path=task/'answer.txt';answer=path.read_text(encoding='utf-8').strip() if path.exists() else None;answers[name]=answer
        checks[name]=(answer==expected.get(name))
        if name in expected and work!=task:checks[name+'_workspace']=(work/'answer.txt').read_text(encoding='utf-8').strip()==answer
    checks['aggregate_out']=output.exists() and json.loads(output.read_text(encoding='utf-8'))==expected
    checks['inputs_unchanged']=all((tasks/name).exists() and digest(tasks/name)==sha for name,sha in before.items())
    checks['no_unexpected_files']=all(p.relative_to(tasks).as_posix() in before or p.name=='answer.txt' for p in tasks.rglob('*') if p.is_file())
    ledgers=[json.loads(p.read_text(encoding='utf-8')) for p in tmp.rglob('budget_*.json')]
    checks['zero_http']=len(ledgers)==1 and ledgers[0]['budget']==0 and not ledgers[0]['events']
    checks['no_research_dependencies']=not (app/'scripts').exists() and not (app/'experiments').exists() and not (app/'tests').exists()
    return {'passed':all(checks.values()),'checks':checks,'answers':answers,'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr,'ledger':ledgers}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    files=runtime_files();hashes={f.relative_to(ROOT).as_posix():digest(f) for f in files}
    with tempfile.TemporaryDirectory(prefix='oj-submission-') as temp:
        base=Path(temp);app=base/'isolated_app';app.mkdir()
        for f in files:
            target=app/f.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
        runs={mode:run_cli(app,base,mode) for mode in ('cli_overrides','budget_environment','token_budget_environment')}
    deps=dependencies();result={'passed':deps['passed'] and all(r['passed'] for r in runs.values()),'python':platform.python_version(),'platform':platform.system(),'runtime_hashes':hashes,'runtime_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),'dependencies':deps,'cli_runs':runs,'docker_tested':False,'linux_tested':False,'note':'Source/CLI acceptance on current Windows host; colleague owns container and Linux checks.'}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':result['passed'],'runtime_files':len(hashes),'dependency_errors':deps['errors'],'cli':{k:v['passed'] for k,v in runs.items()}}))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
