import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sample_api_benchmark import Bridge


class Response:
    def __init__(self, data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self): return json.dumps(self.data).encode()


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'report.json'
        self.report=dict(requests=[],effective_tokens=0,has_unaccounted_request=False)
        self.bridge=Bridge(dict(LLM_BASE_URL='https://api.neuraldeep.ru/v1',
                               LLM_API_KEY='sk-test-only'),3000,self.path,self.report)

    def request(self):
        return asyncio.run(self.bridge.complete('qwen3.8-27b-noreason','test','test',16))

    def test_probe_cost_and_no_secret_in_report(self):
        data=dict(usage=dict(prompt_tokens=16,completion_tokens=2),
                  choices=[dict(message=dict(content='OK'))])
        with patch('sample_api_benchmark.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=Response(data)
            self.assertEqual(self.request(),('OK',16,2,0))
        self.assertAlmostEqual(self.bridge.spent,3.6)
        self.assertNotIn('sk-test-only',self.path.read_text())

    def test_cost_survives_malformed_answer(self):
        with patch('sample_api_benchmark.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=Response(dict(usage=dict(prompt_tokens=16,completion_tokens=2)))
            with self.assertRaises(RuntimeError): self.request()
        self.assertAlmostEqual(self.bridge.spent,3.6)
        self.assertTrue(self.bridge.blocked)
        self.assertFalse(self.report['has_unaccounted_request'])

    def test_uncertain_request_stops_further_calls(self):
        with patch('sample_api_benchmark.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=urllib.error.URLError('test timeout')
            with self.assertRaises(RuntimeError): self.request()
            with self.assertRaises(RuntimeError): self.request()
            self.assertEqual(opener.return_value.open.call_count,1)
        self.assertTrue(self.report['has_unaccounted_request'])

    def test_zero_budget_never_calls_api(self):
        self.bridge.budget=0
        with patch('sample_api_benchmark.urllib.request.build_opener') as opener:
            with self.assertRaises(RuntimeError): self.request()
            opener.assert_not_called()

    def test_default_call_limit_still_four(self):
        data=dict(usage=dict(prompt_tokens=16,completion_tokens=2),
                  choices=[dict(message=dict(content='OK'))])
        with patch('sample_api_benchmark.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=Response(data)
            for _ in range(4): self.request()
            with self.assertRaises(RuntimeError): self.request()
            self.assertEqual(opener.return_value.open.call_count,4)


if __name__=='__main__': unittest.main()
