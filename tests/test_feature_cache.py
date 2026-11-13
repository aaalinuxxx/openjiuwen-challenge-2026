"""Repeated feature discovery must ignore generated Python bytecode."""
import json,tempfile,unittest
from pathlib import Path
from harness.planner.feature_extractor import extract_task_features
class FeatureCacheTests(unittest.TestCase):
    def test_repeated_probes_do_not_write_cache_or_change_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'task.json').write_text(json.dumps(dict(task_id='x',task_type='coding',instruction='Fix mylib.py.',reward=3)))
            (root/'mylib.py').write_text('def f(): return 0\n')
            (root/'test_f.py').write_text('import unittest\nfrom mylib import f\nclass Tests(unittest.TestCase):\n def test_f(self): self.assertEqual(f(),1)\nif __name__=="__main__":unittest.main()\n')
            _,first=extract_task_features(root);_,second=extract_task_features(root)
            self.assertEqual(first,second);self.assertEqual(first.initial_tests_failed,1)
            self.assertFalse((root/'__pycache__').exists())
            (root/'__pycache__').mkdir();(root/'__pycache__/mylib.cpython-test.pyc').write_bytes(b'x'*4096)
            (root/'legacy.pyc').write_bytes(b'x'*512)
            _,cached=extract_task_features(root);self.assertEqual(cached,first)
if __name__=='__main__':unittest.main()
