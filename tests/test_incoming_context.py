"""Incoming KB retrieval controls; original relation directions stay intact."""
import unittest
from harness.agents.kb_context import build_kb_context
class IncomingContextTests(unittest.TestCase):
    def context(self,q,kb,**kwargs):return build_kb_context(q,kb,include_incoming=True,**kwargs)
    def test_inverse_card_is_retrieved_without_inverting_fact(self):
        kb={'Lina':{'tutor':'Ada'},'Nora':{'tutor':'Lina'},'Vera':{'tutor':'Other'}}
        self.assertEqual(build_kb_context('Who has tutor Lina?',kb).names,('Lina',))
        c=self.context('Who has tutor Lina?',kb)
        self.assertEqual(c.names,('Lina','Nora'));self.assertIn('# Nora\ntutor: Lina',c.text)
        self.assertNotIn('tutor: Nora',c.text);self.assertFalse(c.complete_kb)
    def test_forward_answer_survives_incoming_hub(self):
        kb={'Root':{'mentor':'Middle'},'Middle':{'employer':'Company'},'Company':{'city':'Bern'}}
        kb.update({f'Admirer {i}':{'mentor':'Root'} for i in range(100)})
        c=self.context('Root',kb,max_records=3)
        self.assertEqual(c.names,('Root','Middle','Company'));self.assertIn('Bern',c.text)
        self.assertIn('record_limit',c.limits);self.assertFalse(c.complete_kb)
    def test_both_edge_directions_obey_depth(self):
        kb={'Root':{'kind':'Person'},'Child':{'tutor':'Root'},'Grandchild':{'tutor':'Child'}}
        self.assertEqual(self.context('Root',kb,max_hops=0).names,('Root',))
        c=self.context('Root',kb,max_hops=1)
        self.assertEqual(c.names,('Root','Child'));self.assertIn('depth_limit',c.limits)
        self.assertEqual(self.context('Root',kb,max_hops=2).names,('Root','Child','Grandchild'))
    def test_byte_limit_keeps_whole_records_and_partial_flag(self):
        kb={'Анна':{'kind':'Person'},'Борис':{'tutor':'Анна'}}
        original=build_kb_context('Анна',kb)
        c=self.context('Анна',kb,max_bytes=len(original.text.encode('utf-8')))
        self.assertEqual(c.text,original.text);self.assertFalse(c.complete_kb)
        self.assertIn('byte_limit',c.limits)
    def test_conflicting_incoming_alternatives_preserved(self):
        kb={'Root':{'kind':'Person'},'Other':{'kind':'Person'},'Child':{'tutor':'Root','_conflicts':{'tutor':{'Root':['a.md'],'Other':['b.md']}}}}
        c=self.context('Root',kb)
        for x in ('Child','CONFLICT [Other | Root]','a.md','b.md'):self.assertIn(x,c.text)
    def test_case_collision_is_not_fuzzily_resolved(self):
        kb={'ROOT':{'born':'1980'},'Root':{'born':'1990'},'Child':{'tutor':'root'}}
        c=self.context('Who has tutor Root?',kb)
        self.assertEqual(set(c.names),set(kb));self.assertIn('1980',c.text);self.assertIn('1990',c.text)
    def test_cycles_and_input_order_are_deterministic(self):
        kb={'A':{'mentor':'B'},'B':{'mentor':'C'},'C':{'mentor':'A'},'D':{'mentor':'B'}}
        left=self.context('A',kb);right=self.context('A',dict(reversed(list(kb.items()))))
        self.assertEqual(left,right);self.assertEqual(len(left.names),len(set(left.names)))
    def test_metadata_does_not_create_edges(self):
        kb={'Root':{'kind':'Person'},'Child':{'_file':'Root','_field_names':{'Root':['Root']},'note':'unrelated'}}
        self.assertEqual(self.context('Root',kb).names,('Root',))
    def test_option_requires_boolean(self):
        with self.assertRaises(ValueError):build_kb_context('x',{},include_incoming=1)
if __name__=='__main__':unittest.main()
