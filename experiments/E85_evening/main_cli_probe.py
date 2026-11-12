import os,sys,runpy,shutil,tempfile,json
from pathlib import Path
os.environ.setdefault('USERPROFILE',r'C:\Users\PC')
from unittest.mock import patch
root=Path.cwd()
sys.path.insert(0,str(root))
from harness.agents.base_harness import OpenJiuwenLLMBridge
with tempfile.TemporaryDirectory(prefix='oj-main-cli-') as tmp:
    taskroot=Path(tmp)/'tasks';taskroot.mkdir()
    src=root/'experiments/E77_mixed_integration/tasks/pilot_known_or_failure'
    shutil.copytree(src,taskroot/src.name)
    sys.argv=['run_agent.py','--profile','validated','--tasks-dir',str(taskroot),'--budget','0','--max-api-calls','0']
    with patch.object(OpenJiuwenLLMBridge,'_get_transport',side_effect=AssertionError('HTTP forbidden')):
        try:runpy.run_path(str(root/'run_agent.py'),run_name='__main__')
        except SystemExit as e:
            if e.code:raise
    answer=(taskroot/src.name/'answer.txt').read_text().strip()
    assert answer=='30',answer
    print(json.dumps(dict(main_cli_passed=True,answer=answer,actual_http_calls=0)))
