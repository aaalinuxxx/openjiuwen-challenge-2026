import asyncio
from pathlib import Path
import tempfile
import unittest

from harness.config import TaskContext
from harness.agents.search_solver import solve_search_task

class SearchConflictResponseTests(unittest.IsolatedAsyncioTestCase):
    async def run_reply(self, reply, extra_card=None, question='Return the headquarters city of Orbit.'):
        class Bridge:
            async def complete(self, **payload):
                return reply, 20, 3, 0
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'kb').mkdir()
            (root/'kb/a.md').write_text('# Orbit\nHeadquarters: Bern\n',encoding='utf-8')
            (root/'kb/b.md').write_text('# Orbit\nHeadquarters: Oslo\n',encoding='utf-8')
            if extra_card:
                (root/'kb/c.md').write_text(extra_card,encoding='utf-8')
            ctx=TaskContext('conflict','search',question,1,root,root,1000,False)
            return await solve_search_task(ctx,Bridge())

    async def test_conflict_brackets_not_submitted_as_answer(self):
        result=await self.run_reply('CONFLICT [Bern | Oslo]')
        self.assertEqual(result.status,'UNKNOWN')
        self.assertIsNone(result.answer)
        self.assertEqual((result.input_tokens,result.output_tokens),(20,3))

    async def test_bare_conflict_not_submitted_as_answer(self):
        for reply in ('CONFLICT', 'conflict.'):
            with self.subTest(reply=reply):
                result=await self.run_reply(reply)
                self.assertEqual(result.status,'UNKNOWN')
                self.assertIsNone(result.answer)

    async def test_conflict_colon_not_submitted_as_answer(self):
        result=await self.run_reply('conflict: Bern, Oslo')
        self.assertEqual(result.status,'UNKNOWN')
        self.assertIsNone(result.answer)

    async def test_exact_literal_value_is_not_a_refusal_marker(self):
        value='CONFLICT: A Novel'
        result=await self.run_reply(value,'# Book\nTitle: '+value+'\n','Return the title of Book.')
        self.assertEqual((result.status,result.answer),('SOLVED',value))

    async def test_normal_answer_keeps_existing_behavior(self):
        result=await self.run_reply('The Conflict Museum','# Museum\nName: The Conflict Museum\n','Return the name of Museum.')
        self.assertEqual((result.status,result.answer),('SOLVED','The Conflict Museum'))

    async def test_existing_refusal_is_preserved(self):
        result=await self.run_reply('UNSOLVABLE')
        self.assertEqual(result.status,'UNSOLVABLE')
        self.assertIsNone(result.answer)

if __name__=='__main__': unittest.main()
