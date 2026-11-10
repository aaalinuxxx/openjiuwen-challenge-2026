from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.agents.search_solver import _resolve_graph_query

class SearchGraphTests(unittest.TestCase):
    def setUp(self):
        self.kb={'Ada Stone':{'_file':'a.md','mentor':'Bela Moss','born':'1991'},
                 'Bela Moss':{'_file':'b.md','employer':'Orbit Labs','mentor':'Ada Stone'},
                 'Orbit Labs':{'_file':'c.md','headquarters':'Lima','founded':'2008'}}

    def test_trace_and_multi_hop(self):
        result=_resolve_graph_query("In which city is the headquarters of Ada Stone's mentor's employer?",self.kb)
        self.assertEqual(result[:2],('SOLVED','Lima'))
        for filename in ('a.md','b.md','c.md'): self.assertIn(filename,result[2])

    def test_finite_path_can_cross_cycle(self):
        result=_resolve_graph_query("In which year was Ada Stone's mentor's mentor born?",self.kb)
        self.assertEqual(result[:2],('SOLVED','1991'))

    def test_case_and_typographic_apostrophe(self):
        result=_resolve_graph_query('In which city is the headquarters of ada stone’s mentor’s employer?',self.kb)
        self.assertEqual(result[:2],('SOLVED','Lima'))

    def test_historical_constraint_not_ignored(self):
        self.assertIsNone(_resolve_graph_query("In which city is the headquarters of Bela Moss's employer in 1999?",self.kb))

    def test_multiple_questions_not_partially_answered(self):
        self.assertIsNone(_resolve_graph_query('In which year was Ada Stone born? In which year was Orbit Labs founded?',self.kb))

    def test_case_collision_requires_resolution(self):
        self.kb['ADA STONE']={'_file':'duplicate.md','born':'1992'}
        self.assertEqual(_resolve_graph_query('In which year was Ada Stone born?',self.kb)[0],'UNKNOWN')

    def test_broken_link_and_missing_field(self):
        del self.kb['Orbit Labs']
        self.assertEqual(_resolve_graph_query("In which city is the headquarters of Bela Moss's employer?",self.kb)[0],'UNSOLVABLE')
        self.assertEqual(_resolve_graph_query('In which year was Bela Moss born?',self.kb)[0],'UNSOLVABLE')

if __name__=='__main__': unittest.main()
