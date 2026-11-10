"""Исчерпывающее тестирование отказоустойчивости транспорта RobustHTTPTransport на всех типах сбоев."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
import unittest
from unittest.mock import patch, MagicMock
import httpx

from harness.agents.base_harness import RobustHTTPTransport, ProxyBudgetExhausted, TransientNetworkError


class ResilientTransportComprehensiveTests(unittest.TestCase):

    def setUp(self):
        self.transport = RobustHTTPTransport(
            base_url="https://api.test/v1",
            api_key="test-key",
            max_retries=3
        )

    # 1. Сценарий: 429 Too Many Requests с заголовком Retry-After
    def test_01_rate_limit_with_retry_after(self):
        async def _test():
            resp_429 = MagicMock(status_code=429, headers={"Retry-After": "0"})
            resp_200 = MagicMock(status_code=200)
            resp_200.json.return_value = {"choices": [{"message": {"content": "Answer 42"}}]}

            with patch("httpx.AsyncClient.post", side_effect=[resp_429, resp_200]):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["message"]["content"], "Answer 42")

        asyncio.run(_test())

    # 2. Сценарий: 502 Bad Gateway / 503 Service Unavailable (сбой Nginx/GPU)
    def test_02_server_outage_502_503_recovers(self):
        async def _test():
            resp_502 = MagicMock(status_code=502)
            resp_503 = MagicMock(status_code=503)
            resp_200 = MagicMock(status_code=200)
            resp_200.json.return_value = {"choices": [{"message": {"content": "Recovered"}}]}

            with patch("httpx.AsyncClient.post", side_effect=[resp_502, resp_503, resp_200]):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["message"]["content"], "Recovered")

        asyncio.run(_test())

    # 3. Сценарий: 504 Gateway Timeout
    def test_03_gateway_timeout_504_recovers(self):
        async def _test():
            resp_504 = MagicMock(status_code=504)
            resp_200 = MagicMock(status_code=200)
            resp_200.json.return_value = {"choices": [{"message": {"content": "Timeout Recovered"}}]}

            with patch("httpx.AsyncClient.post", side_effect=[resp_504, resp_200]):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["message"]["content"], "Timeout Recovered")

        asyncio.run(_test())

    # 4. Сценарий: Стена бюджета (403 Forbidden / 401 Unauthorized) — Fast Fail
    def test_04_budget_exhausted_fast_fails_without_retries(self):
        async def _test():
            resp_403 = MagicMock(status_code=403, text="Quota exceeded")

            with patch("httpx.AsyncClient.post", return_value=resp_403) as mock_post:
                with self.assertRaises(ProxyBudgetExhausted):
                    await self.transport.send({"model": "test"})
                # Должен быть строго 1 запрос без бесполезных ретраев
                self.assertEqual(mock_post.call_count, 1)
                self.assertTrue(self.transport._proxy_exhausted)

                # Следующий запрос должен быть заблокирован локально до выхода в сеть
                with self.assertRaises(ProxyBudgetExhausted):
                    await self.transport.send({"model": "test"})
                self.assertEqual(mock_post.call_count, 1)

        asyncio.run(_test())

    # 5. Сценарий: Сетевой разрыв соединения (ConnectError)
    def test_05_connect_error_recovers(self):
        async def _test():
            resp_200 = MagicMock(status_code=200)
            resp_200.json.return_value = {"choices": [{"message": {"content": "Connected"}}]}

            with patch("httpx.AsyncClient.post", side_effect=[httpx.ConnectError("Connection refused"), resp_200]):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["message"]["content"], "Connected")

        asyncio.run(_test())

    # 6. Сценарий: Таймаут чтения генерации (ReadTimeout > 60с)
    def test_06_read_timeout_recovers(self):
        async def _test():
            resp_200 = MagicMock(status_code=200)
            resp_200.json.return_value = {"choices": [{"message": {"content": "Finished"}}]}

            with patch("httpx.AsyncClient.post", side_effect=[httpx.ReadTimeout("Server took too long"), resp_200]):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["message"]["content"], "Finished")

        asyncio.run(_test())

    # 7. Сценарий: Поврежденный ответ (HTML-страница вместо валидного JSON)
    def test_07_corrupted_json_or_html_recovers(self):
        async def _test():
            resp_html = MagicMock(status_code=200, text="<html><body>Bad Gateway</body></html>")
            resp_html.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)

            resp_valid = MagicMock(status_code=200)
            resp_valid.json.return_value = {"choices": [{"message": {"content": "Valid JSON"}}]}

            with patch("httpx.AsyncClient.post", side_effect=[resp_html, resp_valid]):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["message"]["content"], "Valid JSON")

        asyncio.run(_test())

    # 8. Сценарий: Детекция обрезки генерации (finish_reason: length)
    def test_08_truncated_generation_detected(self):
        async def _test():
            resp_len = MagicMock(status_code=200)
            resp_len.json.return_value = {
                "choices": [{
                    "finish_reason": "length",
                    "message": {"content": "def partial_func("}
                }]
            }

            with patch("httpx.AsyncClient.post", return_value=resp_len):
                data = await self.transport.send({"model": "test"})
                self.assertEqual(data["choices"][0]["finish_reason"], "length")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()