import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compact_math_benchmark import COMPACT_MATH_PROMPT,completion
class CompactPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_changes_only_math_system_preserving_full_instruction(self):
        received=[]
        async def original(*args,**kwargs):received.append((args,kwargs));return ('code',10,20,0)
        wrapped=completion(original,{'math_a'})
        user='Find x, subject to x>4; write answer.txt. Do not discard any constraint.'
        result=await wrapped(SimpleNamespace(task_id='math_a'),'model','old',user,max_tokens=200,temperature=0)
        self.assertEqual(received[0][0][2],COMPACT_MATH_PROMPT)
        self.assertEqual(received[0][0][3],user)
        self.assertEqual(received[0][1],{'max_tokens':200,'temperature':0})
        self.assertEqual(result,('code',10,20,0))
        self.assertEqual(len(received),1)
    async def test_non_math_prompt_and_caps_unchanged(self):
        received=[]
        async def original(*args,**kwargs):received.append((args,kwargs));return ('code',10,20,0)
        await completion(original,{'math_a'})(SimpleNamespace(task_id='data_a'),'model','original','question',96,0.2)
        self.assertEqual(received[0][0][2:4],('original','question'))
        self.assertEqual(received[0][1],{'max_tokens':96,'temperature':0.2})
    async def test_errors_propagate_without_retry(self):
        received=[]
        async def original(*args,**kwargs):received.append(1);raise TimeoutError()
        with self.assertRaises(TimeoutError):await completion(original,{'math_a'})(SimpleNamespace(task_id='math_a'),'model','old','question')
        self.assertEqual(len(received),1)
if __name__=='__main__':unittest.main()
