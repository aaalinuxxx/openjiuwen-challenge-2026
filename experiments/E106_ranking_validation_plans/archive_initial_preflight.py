import hashlib,json,sys,zipfile
from pathlib import Path
root=Path.cwd()
dest=root/'experiments/E106_ranking_validation_plans'
records=[]
for name in sys.argv[1:]:
    directory=(root/'experiments'/name).resolve()
    assert directory.parent==(root/'experiments').resolve() and name.startswith('E107_validation_') and '_offline_' in name
    archive=dest/(name+'_initial.zip')
    manifest={}
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file():
                b=p.read_bytes();rel=p.relative_to(directory).as_posix()
                z.writestr(rel,b);manifest[rel]=hashlib.sha256(b).hexdigest()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in manifest.items())
    records.append(dict(directory=name,archive=archive.name,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest))
(dest/'initial_offline_archives.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(archives=len(records),verified=True)))
