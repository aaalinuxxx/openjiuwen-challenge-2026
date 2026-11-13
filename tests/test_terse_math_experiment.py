import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from terse_math_benchmark import BASELINE_MATH_PROMPT,TERSE_SUFFIX,completion
class TersePromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_append_only_and_preserve_arguments(self):
        received=[]
        async def original(*args,**kwargs):received.append((args,kwargs));return ('print(1)',3,4,0)
        wrapped=completion(original,{'math_a'})
        await wrapped(SimpleNamespace(task_id='math_a'),'model',BASELINE_MATH_PROMPT,'all constraints',200,0)
        self.assertEqual(received[0][0][2],BASELINE_MATH_PROMPT+TERSE_SUFFIX)
        self.assertEqual(received[0][0][3],'all constraints')
        self.assertEqual(received[0][1],{'max_tokens':200,'temperature':0})
        await wrapped(SimpleNamespace(task_id='data_a'),'other','data prompt','data question',99,0)
        self.assertEqual(received[1][0][2:4],('data prompt','data question'))
    async def test_reject_baseline_drift_before_transport(self):
        async def original(*args,**kwargs):self.fail('transport must not run')
        with self.assertRaises(ValueError):await completion(original,{'math_a'})(SimpleNamespace(task_id='math_a'),'model','changed','question')
if __name__=='__main__':unittest.main()
