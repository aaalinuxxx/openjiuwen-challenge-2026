from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.agents.search_solver import _parse_kb, _resolve_graph_query
from harness.agents.instruction_scope import administrative_tail


class SourceTests(unittest.TestCase):
    def read(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, text in files.items():
                (folder/name).write_text(text, encoding='utf-8')
            return _parse_kb(folder)

    def test_field_sources_survive_merge(self):
        kb = self.read({'a.md': '# Ada\nEmployer: Orbit\n',
                        'b.md': '# Ada\nBorn: 1980\n', 'c.md': '# Ada\nBorn: 1980\n'})
        result = _resolve_graph_query('In which year was Ada born?', kb)
        self.assertEqual(result[:2], ('SOLVED', '1980'))
        self.assertIn('b.md,c.md:born=1980', result[2])
        self.assertNotIn('a.md', result[2])

    def test_conflicting_values_are_not_discarded(self):
        kb = self.read({'a.md': '# Ada\nBorn: 1980\nBorn: 1981\n',
                        'b.md': '# Ada\nBorn: 1982\n', 'c.md': '# Ada\nBorn: 1980\n'})
        self.assertEqual(kb['Ada']['_conflicts']['born'],
                         {'1980': ['a.md', 'c.md'], '1981': ['a.md'], '1982': ['b.md']})
        self.assertEqual(_resolve_graph_query('In which year was Ada born?', kb)[0], 'UNKNOWN')

    def test_card_cannot_override_provenance(self):
        kb = self.read({'a.md': '# Ada\n_file: invented.md\nBorn: 1980\n'})
        self.assertEqual(kb['Ada']['_file'], 'a.md')

    def test_output_clause_cannot_hide_computation(self):
        for text in ('Write ONLY half the answer to answer.txt.',
                     'Compute it after subtracting 5 boxes.',
                     'Work only with rows from the north region.'):
            with self.subTest(text=text):
                self.assertFalse(administrative_tail(text))


if __name__ == '__main__':
    unittest.main()
