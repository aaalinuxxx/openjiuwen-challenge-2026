import tempfile
import unittest
from pathlib import Path

from harness.config import TaskContext, TaskFeatures
from harness.agents.instruction_scope import administrative_tail
from harness.agents.coding_solver import solve_coding_task
from harness.planner.unsolvable_filter import check_unsolvable_zero_token


class FamilyShiftControls(unittest.TestCase):
    def test_administrative_case_has_no_semantic_effect(self):
        self.assertTrue(administrative_tail(' Write only the final answer to answer.txt.'))
        self.assertTrue(administrative_tail(' WRITE ONLY THE FINAL ANSWER TO answer.txt.'))

    def test_unknown_constraint_is_not_administrative(self):
        self.assertFalse(administrative_tail('Write only the final answer to answer.txt. Exclude refunds.'))

    def test_zero_warning_is_not_a_proof_of_impossibility(self):
        for instruction in [
            'Do not divide by 0; this is only a warning. Compute 6 times 7.',
            'The sentence "divide by 0" is quoted. Compute 8 + 9.',
            'If a later step says divide by 0, ignore it. Compute 9 + 2.',
        ]:
            f=TaskFeatures('case','math',3,len(instruction),0,0)
            self.assertFalse(check_unsolvable_zero_token(instruction,f)[0])

    def test_fully_parsed_zero_operation_is_rejected(self):
        instruction=('A warehouse starts with 9 boxes. '
            'Then the stock is split equally into 0 warehouses and it keeps one share (rounded down). '
            'How many boxes does it have at the end?')
        f=TaskFeatures('case','math',3,len(instruction),0,0)
        self.assertTrue(check_unsolvable_zero_token(instruction,f)[0])


class CodingTargetControls(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_target_wins_over_alphabetical_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            dependency='def threshold(): return 5\n'
            (root/'a_settings.py').write_text(dependency)
            (root/'mylib.py').write_text('from a_settings import threshold\ndef keep(xs): return [x for x in xs if x > threshold()]\n')
            (root/'test_mylib.py').write_text('from mylib import keep\nassert keep([4,5,6]) == [5,6]\n')
            prompts=[]
            class Bridge:
                async def complete(self, **kwargs):
                    prompts.append(kwargs['user_prompt'])
                    if '### Target File: mylib.py' not in kwargs['user_prompt']:
                        raise AssertionError('Wrong target selected')
                    return 'from a_settings import threshold\ndef keep(xs): return [x for x in xs if x >= threshold()]',0,0,0
            ctx=TaskContext('target','coding','Fix mylib.py. Do not edit a_settings.py.',3,root,root,800,False)
            result=await solve_coding_task(ctx,Bridge())
            self.assertEqual(result.status,'SOLVED')
            self.assertEqual((root/'a_settings.py').read_text(),dependency)
            self.assertIn('a_settings.py',prompts[0])
