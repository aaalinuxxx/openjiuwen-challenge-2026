"""Factual support tests; no claim of complete natural-language verification."""
import json
from pathlib import Path
import tempfile
import unittest

from harness.agents.search_solver import _parse_kb
from harness.agents.search_evidence import verify_evidence, solve_evidence_search
from harness.config import TaskContext

ROOT=Path(__file__).resolve().parents[1]

class EvidenceChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def case(self,name):
        case=next(c for c in json.loads((ROOT/'experiments/E55_evidence/cases.json').read_text(encoding='utf-8')) if c['id']==name)
        root=self.root/name
        for filename,content in case['files'].items():
            path=root/filename
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8')
        return case,_parse_kb(root/'kb')

    def verify(self,name,status,answer,evidence,complete=True):
        case,entities=self.case(name)
        return verify_evidence(case['question'],entities,tuple(entities),complete,
            dict(status=status,answer=answer,evidence=evidence))

    def test_complete_chain(self):
        result=self.verify('clear_chain','SOLVED','Vilnius',[
            ['Felix Orr','mentor'],['Sara Glen','employer'],['Maple Glass','headquarters']])
        self.assertEqual(result[:2],('SOLVED','Vilnius'))
        for source in ('a.md','b.md','c.md'): self.assertIn(source,result[2])

    def test_wrong_answer_rejected(self):
        self.assertEqual(self.verify('clear_chain','SOLVED','Oslo',[
            ['Felix Orr','mentor'],['Sara Glen','employer'],['Maple Glass','headquarters']])[0],'UNKNOWN')

    def test_terminal_conflict_cannot_be_cherry_picked(self):
        self.assertEqual(self.verify('needed_conflict','SOLVED','Valencia',[
            ['Kira Sol','employer'],['Aster Works','headquarters']])[0],'UNKNOWN')

    def test_intermediate_conflict_cannot_be_cherry_picked(self):
        self.assertEqual(self.verify('conflicting_link','SOLVED','Split',[
            ['Iris Pike','mentor'],['Leon Vale','employer'],['Red Maple','headquarters']])[0],'UNKNOWN')

    def test_irrelevant_conflict_is_allowed(self):
        self.assertEqual(self.verify('unrelated_conflict','SOLVED','Graz',[
            ['Daria Holt','employer'],['Blue Willow','headquarters']])[:2],('SOLVED','Graz'))

    def test_wrong_root_and_disconnected_path_rejected(self):
        for path in ([['Sara Glen','employer'],['Maple Glass','headquarters']],
                     [['Felix Orr','mentor'],['Maple Glass','headquarters']]):
            with self.subTest(path=path):
                self.assertEqual(self.verify('clear_chain','SOLVED','Vilnius',path)[0],'UNKNOWN')

    def test_wrong_or_private_field_rejected(self):
        for field in ('founded','_file','invented'):
            self.assertEqual(self.verify('missing_field','SOLVED','2012',[['Meadow Studio',field]])[0],'UNKNOWN')

    def test_missing_fact_requires_complete_kb_and_refusal(self):
        path=[['Meadow Studio','headquarters']]
        self.assertEqual(self.verify('missing_field','UNSOLVABLE',None,path)[0],'UNSOLVABLE')
        self.assertEqual(self.verify('missing_field','UNSOLVABLE',None,path,False)[0],'UNKNOWN')
        self.assertEqual(self.verify('missing_field','SOLVED','Oslo',path)[0],'UNKNOWN')

    def test_terminal_conflict_proof_vs_intermediate_abstention(self):
        self.assertEqual(self.verify('needed_conflict','UNSOLVABLE',None,[
            ['Kira Sol','employer'],['Aster Works','headquarters']])[0],'UNSOLVABLE')
        self.assertEqual(self.verify('conflicting_link','UNSOLVABLE',None,[
            ['Iris Pike','mentor'],['Leon Vale','employer']])[0],'UNKNOWN')

    def test_literal_marker_is_valid_value(self):
        self.assertEqual(self.verify('literal_marker','SOLVED','CONFLICT',[
            ['Archive Book','title']])[:2],('SOLVED','CONFLICT'))

    def test_schema_and_missing_evidence_rejected(self):
        case,entities=self.case('literal_marker')
        for doc in (None,[],{},dict(status='SOLVED',answer='CONFLICT',evidence=[]),
                    dict(status='UNSOLVABLE',answer='CONFLICT',evidence=[['Archive Book','title']]),
                    dict(status=[],answer='CONFLICT',evidence=[['Archive Book','title']])):
            with self.subTest(doc=doc):
                self.assertEqual(verify_evidence(case['question'],entities,tuple(entities),True,doc)[0],'UNKNOWN')


class EvidenceUsage(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_json_keeps_usage(self):
        class Bridge:
            async def complete(self,**payload): return 'not json',20,7,0
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'kb').mkdir()
            (root/'kb/a.md').write_text('# Archive Book\nTitle: CONFLICT\n',encoding='utf-8')
            ctx=TaskContext('x','search','Give the title of Archive Book.',1,root,root,900,False)
            result=await solve_evidence_search(ctx,Bridge())
            self.assertEqual(result.status,'UNKNOWN')
            self.assertEqual((result.input_tokens,result.output_tokens),(20,7))

if __name__=='__main__': unittest.main()
