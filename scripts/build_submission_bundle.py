"""Build a deterministic source-only bundle from a passing acceptance manifest."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',type=Path,default=ROOT/'experiments/E128_submission_acceptance/preflight.json')
    parser.add_argument('--acceptance',type=Path,default=ROOT/'experiments/E129_submission_summary.json')
    parser.add_argument('--runtime-source-commit',default='69da4c8eb3a16efaa70292d8c93c8a4cb84a4615')
    args=parser.parse_args()
    pre=json.loads(args.preflight.read_text(encoding='utf-8'))
    audit=json.loads(args.acceptance.read_text(encoding='utf-8'))
    if audit['runtime_sha256']!=pre['runtime_sha256']:raise ValueError('Runtime acceptance mismatch')
    if not pre['passed'] or not audit['accepted']:raise ValueError('Submission acceptance not passed')
    files=pre['runtime_hashes'];out=ROOT/'release';out.mkdir(exist_ok=True)
    path=out/'agent_source.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,sha in sorted(files.items()):
            source=ROOT/name
            if not source.resolve().is_relative_to(ROOT.resolve()) or source.is_symlink():raise ValueError('Invalid source path')
            raw=source.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Runtime changed: '+name)
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,raw)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None and sorted(z.namelist())==sorted(files)
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in files.items())
    manifest=dict(runtime_sha256=pre['runtime_sha256'],files=files,bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bundle_bytes=path.stat().st_size,entrypoint='python /app/run_agent.py --tasks-dir /data/tasks',configuration=audit['configuration'],acceptance_report=args.acceptance.resolve().relative_to(ROOT).as_posix(),acceptance_report_sha256=hashlib.sha256(args.acceptance.read_bytes()).hexdigest(),runtime_source_commit=args.runtime_source_commit,docker_included=False,selected_math_policy=audit.get('selected_arm','baseline'),new_experimental_policies_enabled=audit.get('selected_arm','baseline')!='baseline',research_scripts_included=False)
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (out/'tested_environment.json').write_text(json.dumps(dict(python=pre['python'],platform=pre['platform'],packages=pre['dependencies']['packages'],note='Observed working host versions, not a cross-platform lockfile'),indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(files),'bytes':path.stat().st_size,'bundle_sha256':manifest['bundle_sha256'],'runtime_sha256':pre['runtime_sha256']}))
if __name__=='__main__':main()
