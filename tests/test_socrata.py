from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from marketing_lead.socrata import SocrataDataset, fetch_rows


class _FakeResponse:
    def __init__(self, payload: object):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class SocrataTests(unittest.TestCase):
    def test_fetch_rows_builds_url_and_returns_dict_rows(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["timeout"] = timeout
            return _FakeResponse([{"name": "A"}, {"name": "B"}, "skip-me"])

        dataset = SocrataDataset(base_url="https://data.example.com", dataset_id="abcd-1234", app_token="tok")
        with patch("marketing_lead.socrata.urlopen", side_effect=fake_urlopen):
            rows = fetch_rows(dataset, limit=10, where="zip='90015'", select="name,zip")

        self.assertEqual(len(rows), 2)
        self.assertIn("/resource/abcd-1234.json", captured["url"])
        self.assertIn("%24limit=10", captured["url"])
        self.assertEqual(captured["timeout"], 20)
        self.assertEqual(captured["headers"].get("X-app-token"), "tok")


if __name__ == "__main__":
    unittest.main()
