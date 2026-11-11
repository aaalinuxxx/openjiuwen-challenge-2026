"""Losslessness and boundedness controls for experimental KB table encoding."""
from pathlib import Path
import json
import tempfile
import unittest

from harness.agents.kb_context import build_kb_context
from harness.agents.kb_compaction import table_context, decode_table, PREFIX
from harness.agents.search_solver import _parse_kb

ROOT = Path(__file__).resolve().parents[1]

class KBCompactionTests(unittest.TestCase):
    def test_fixture_roundtrip_keeps_values_conflicts_sources(self):
        cases = json.loads((ROOT/'experiments/E52_kb_compaction/cases.json').read_text(encoding='utf-8'))
        encoded = 0
        for case in cases:
            with self.subTest(case=case['id']), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                for name, content in case['files'].items():
                    path = root/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding='utf-8')
                entities = _parse_kb(root/'kb')
                plain = build_kb_context(case['question'], entities)
                compact = table_context(case['question'], entities)
                self.assertEqual((plain.names, plain.complete_kb, plain.limits),
                                 (compact.names, compact.complete_kb, compact.limits))
                self.assertLessEqual(len(compact.text.encode()), len(plain.text.encode()))
                if not compact.text.startswith(PREFIX):
                    self.assertEqual(compact, plain)
                    continue
                encoded += 1
                decoded = decode_table(compact.text)
                for name in plain.names:
                    record = entities[name]
                    expected = {}
                    sources = set()
                    for field, value in record.items():
                        if field.startswith('_'):
                            continue
                        conflict = record['_conflicts'].get(field)
                        expected[field] = {'CONFLICT': sorted(conflict)} if conflict else value
                    for files in record['_sources'].values():
                        sources.update(files)
                    for conflict in record['_conflicts'].values():
                        for files in conflict.values():
                            sources.update(files)
                    self.assertEqual(decoded[name], dict(fields=expected, sources=sorted(sources)))
        self.assertGreater(encoded, 0)

    def test_short_sparse_context_falls_back_verbatim(self):
        entities = {'Ada': {'born': '1991', '_file': 'a.md'}}
        self.assertEqual(table_context('Ada', entities), build_kb_context('Ada', entities))

    def test_limits_and_empty_selection_unchanged(self):
        entities = {str(i): {**{('long_field_name_'+str(k)): str(k) for k in range(10)},
                             'mentor': str((i+1)%8)} for i in range(8)}
        for options in ({'max_records': 2}, {'max_bytes': 1}, {'max_hops': 0}, {'max_hops': 2}):
            with self.subTest(options=options):
                plain = build_kb_context('0', entities, **options)
                compact = table_context('0', entities, **options)
                self.assertEqual((plain.names, plain.complete_kb, plain.limits),
                                 (compact.names, compact.complete_kb, compact.limits))
                self.assertLessEqual(len(compact.text.encode()), len(plain.text.encode()))

    def test_literal_null_quotes_and_conflicts_are_not_conflated(self):
        entities = {f'Person {i}': {
            **{f'repeated_long_field_{k}': 'я "x" \\n null [CONFLICT]' for k in range(10)},
            'literal': 'null', '_file': f'{i}.md'} for i in range(4)}
        entities['Person 0']['_conflicts'] = {'literal': {'null': ['a.md'], 'None': ['b.md']}}
        context = table_context('no named person', entities)
        decoded = decode_table(context.text)
        self.assertEqual(decoded['Person 0']['fields']['literal'], {'CONFLICT': ['None', 'null']})
        self.assertEqual(decoded['Person 1']['fields']['literal'], 'null')
        self.assertEqual(decoded['Person 2']['fields']['repeated_long_field_0'], 'я "x" \\n null [CONFLICT]')

    def test_input_order_does_not_change_encoding(self):
        entities = {f'Person {i}': {f'long_field_name_{k}': str(k) for k in range(10)} for i in range(4)}
        reversed_entities = {name: dict(reversed(list(fields.items())))
                             for name, fields in reversed(list(entities.items()))}
        self.assertEqual(table_context('no named person', entities),
                         table_context('no named person', reversed_entities))

if __name__ == '__main__':
    unittest.main()
