"""Regressions from E107 plus adversarial controls; no API calls."""
from pathlib import Path
import tempfile
import unittest
from harness.agents.search_solver import _parse_kb, solve_search_task
from harness.agents.kb_context import build_kb_context
from harness.agents.coding_target import select_coding_target
from harness.config import TaskContext

class RefusalWhitespaceTests(unittest.IsolatedAsyncioTestCase):
    async def reply(self, text, extra='', partial=False):
        class Bridge:
            async def complete(self, **payload): return text, 20, 3, 0
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'kb').mkdir()
            (root/'kb/a.md').write_text('# Orbit\nLaunch: 2001\nLaunch: 2004\n'+extra,encoding='utf-8')
            if partial:(root/'kb/b.md').write_text('# Omitted\nName: Elsewhere\n',encoding='utf-8')
            ctx=TaskContext('x','search','Return the requested value from Orbit.',1,root,root,1000,False)
            return await solve_search_task(ctx,Bridge())
    async def test_whitespace_refusals_keep_usage(self):
        for text in ('UN SOLVABLE','un\tsolvable.','UN\nSOLVABLE','UN\u00a0SOLVABLE','UNSOLVABLE','No unique answer.\nUNSOLVABLE'):
            with self.subTest(text=text):
                r=await self.reply(text)
                self.assertEqual((r.status,r.answer),('UNSOLVABLE',None))
                self.assertEqual((r.input_tokens,r.output_tokens),(20,3))
    async def test_unknown_and_partial_kb_abstain(self):
        for text,partial in [('UN KNOWN',False),('UN SOLVABLE',True)]:
            r=await self.reply(text,partial=partial)
            self.assertEqual((r.status,r.answer),('UNKNOWN',None))
    async def test_literal_service_marker_is_preserved(self):
        for text in ('UN SOLVABLE','UNKNOWN','UNSOLVABLE'):
            r=await self.reply(text,'Title: '+text+'\n')
            self.assertEqual((r.status,r.answer),('SOLVED',text))
    async def test_longer_names_are_not_service_markers(self):
        r=await self.reply('Unknown Soldier','Title: Unknown Soldier\n')
        self.assertEqual((r.status,r.answer),('SOLVED','Unknown Soldier'))

class KBFieldSpellingTests(unittest.TestCase):
    def context(self,content):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'card.md').write_text(content,encoding='utf-8')
            entities=_parse_kb(p)
            return entities,build_kb_context('Which product is latest?',entities)
    def test_model_context_preserves_exact_product_names(self):
        entities,context=self.context('# Products\nMistral: 2034\nKestrel: 2031\n')
        self.assertEqual(entities['Products']['mistral'],'2034')
        self.assertIn('Mistral: 2034',context.text)
        self.assertNotIn('mistral: 2034',context.text)
    def test_case_collisions_and_values_remain_visible(self):
        entities,context=self.context('# Products\nMistral: 2034\nmistral: 2031\n')
        self.assertIn('Mistral: CONFLICT [2031 | 2034]',context.text)
        self.assertIn('mistral: CONFLICT [2031 | 2034]',context.text)
        self.assertEqual(set(entities['Products']['_conflicts']['mistral']),{'2034','2031'})
    def test_rendered_spelling_counts_toward_byte_limit(self):
        entities,context=self.context('# Products\nMiSTRAL: 2034\n')
        bounded=build_kb_context('Which product?',entities,max_bytes=10)
        self.assertFalse(bounded.complete_kb)
        self.assertLessEqual(len(bounded.text.encode('utf-8')),10)

class CodingNonmutationTests(unittest.TestCase):
    def test_nonmutation_does_not_forbid_explicit_target(self):
        for clause in ('Do not modify values.','Do not modify matrix.','Do not modify input.','Never change the input list.'):
            with self.subTest(clause=clause):
                p=select_coding_target(clause+' Modify only mylib.py. Do not change tests.',[Path('mylib.py')])
                self.assertEqual(p,Path('mylib.py'))
    def test_source_and_unknown_restrictions_stay_blocking(self):
        for clause in ('Do not modify any files.','Do not modify source.','Do not modify mylib.py.','Do not modify input.py.','Do not modify values or code.'):
            name='input.py' if 'input.py' in clause else 'mylib.py'
            with self.subTest(clause=clause):
                self.assertIsNone(select_coding_target(clause+' Modify only '+name+'.',[Path(name)]))
    def test_nonmutation_does_not_resolve_multiple_targets(self):
        self.assertIsNone(select_coding_target('Do not modify values. Fix bugs.',[Path('a.py'),Path('b.py')]))

if __name__=='__main__':unittest.main()
