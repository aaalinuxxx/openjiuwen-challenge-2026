"""Regression controls for disposable CSV execution and answer delivery."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from harness.config import TaskContext
from harness.agents.data_solver import solve_data_task
from harness.agents.multi_csv import solve_multi_csv_task
from harness.sandbox.executor import run_csv_snippet, run_python_snippet

class CSVExecutionContractTests(unittest.TestCase):
    def test_both_solvers_share_output_and_integrity_rules(self):
        cases = [
            ("open('answer.txt','w').write('35\\n')", 'SOLVED', '35'),
            ("import csv;print(sum(int(r['x']) for r in csv.DictReader(open('a.csv'))))", 'SOLVED', '35'),
            ("open('answer.txt','w').write('35');print(35)", 'SOLVED', '35'),
            ("open('answer.txt','w').write('35');print(99)", 'FAILED', None),
            ("open('answer.txt','w').write('35\\n99');print(99)", 'FAILED', None),
            ("open('answer.txt','w').write('35');print('log\\n35')", 'FAILED', None),
            ("open('answer.txt','w').write('999');raise ValueError('test')", 'FAILED', None),
            ("open('a.csv','w').write('bad');print(35)", 'UNKNOWN', None),
            ("open('extra.txt','w').write('bad');print(35)", 'UNKNOWN', None),
            ("0", 'FAILED', None),
            ("open('answer.txt','w').write('0')", 'SOLVED', '0'),
            ("open('answer.txt','w').close();print(35)", 'FAILED', None),
            ("open('answer.txt','wb').write(bytes([255]))", 'FAILED', None),
            ("import os;os.mkdir('answer.txt');print(35)", 'FAILED', None),
        ]
        for multi in (False, True):
            for code, status, answer in cases:
                with self.subTest(multi=multi, code=code), tempfile.TemporaryDirectory() as temp:
                    root=Path(temp)
                    (root/'a.csv').write_text('x\n10\n25\n',encoding='utf-8')
                    if multi: (root/'b.csv').write_text('y\n1\n',encoding='utf-8')
                    (root/'answer.txt').write_text('previous answer',encoding='utf-8')
                    (root/'protected.txt').write_text('untouched',encoding='utf-8')
                    before={p.name:p.read_bytes() for p in root.iterdir()}
                    ctx=TaskContext('csv','data_analysis',
                        'Read a.csv and b.csv; sum x from a.csv and write answer.txt.' if multi else
                        'Calculate sum x from a.csv and write answer.txt.',3,root,root,700,False)
                    class Bridge:
                        async def complete(self,**kwargs): return code,100,20,0
                    dirs=[]
                    def execute(*args,**kwargs):
                        dirs.append(kwargs['cwd']);return run_python_snippet(*args,**kwargs)
                    with patch('harness.sandbox.executor.run_python_snippet',side_effect=execute):
                        result=asyncio.run((solve_multi_csv_task if multi else solve_data_task)(ctx,Bridge()))
                    self.assertEqual((result.status,result.answer),(status,answer))
                    self.assertEqual(result.effective_cost,30)
                    self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
                    self.assertEqual(len(dirs),1)
                    self.assertNotEqual(dirs[0],root)
                    self.assertFalse(dirs[0].exists())

    def test_timeout_does_not_publish_partial_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);csv=root/'a.csv';csv.write_text('x\n35\n')
            result=run_csv_snippet("import time;open('answer.txt','w').write('999');time.sleep(10)",[csv],timeout_sec=0.1)
            self.assertEqual(result,('FAILED',None,'TimeoutExpired'))
            self.assertEqual(list(root.iterdir()),[csv])
