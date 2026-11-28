#!/usr/bin/env python3
"""Regression tests for official-source monitor parsing and status semantics."""
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_official_sources


class FakeResponse:
    def __init__(self, body, status=200, content_type="text/html; charset=utf-8", url="https://example.test/page"):
        self.body = body.encode("utf-8")
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class OfficialSourceMonitorTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "sample",
            "name": "Официален тестов източник",
            "url": "https://example.test/page",
            "frequency": "месечно",
            "expected_terms": [["бюджет", "бюджета"], ["месечен", "месечни"]],
            "expected": "Месечни бюджетни данни",
            "owner": "Тестова институция",
        }

    def test_expected_topic_terms_produce_ok(self):
        html = "<html><body>Данни за държавния бюджет и месечни таблици.</body></html>"
        with patch.object(check_official_sources.urllib.request, "urlopen", return_value=FakeResponse(html)):
            result = check_official_sources.check(self.source)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["http_status"], 200)
        self.assertIn("тематични термини", result["note"])

    def test_missing_topic_terms_produce_content_mismatch(self):
        html = "<html><body>Добре дошли в официалния сайт.</body></html>"
        with patch.object(check_official_sources.urllib.request, "urlopen", return_value=FakeResponse(html)):
            result = check_official_sources.check(self.source)
        self.assertEqual(result["status"], "content_mismatch")
        self.assertIn("липсват", result["note"])

    def test_sdmx_php_download_endpoints_are_detected_and_deduplicated(self):
        self.assertTrue(check_official_sources.downloadable_link(
            "https://www.nsi.bg/ddb2.1/download_data.php?id=123"
        ))
        self.assertTrue(check_official_sources.downloadable_link(
            "https://www.nsi.bg/ddb2.1/download_dsd.php?id=456"
        ))
        self.assertTrue(check_official_sources.downloadable_link(
            "https://example.test/file.xlsx?download=1"
        ))
        self.assertFalse(check_official_sources.downloadable_link(
            "https://example.test/article"
        ))
        html = (
            '<a href="/ddb2.1/download_data.php?id=1">data</a>'
            '<a href="/ddb2.1/download_data.php?id=1">duplicate</a>'
            '<a href="/ddb2.1/download_dsd.php?id=2">dsd</a>'
        )
        with patch.object(
            check_official_sources.urllib.request, "urlopen",
            return_value=FakeResponse(html, url="https://www.nsi.bg/ddb2.1/?l=bg"),
        ):
            result = check_official_sources.check({
                **self.source,
                "expected_terms": [["data"]],
            })
        self.assertEqual(result["download_links_detected"], 2)

    def test_http_403_is_restricted_not_unavailable(self):
        error = urllib.error.HTTPError(
            self.source["url"], 403, "Forbidden", hdrs=None, fp=None
        )
        with patch.object(check_official_sources.urllib.request, "urlopen", side_effect=error):
            result = check_official_sources.check(self.source)
        self.assertEqual(result["status"], "restricted")
        self.assertIn("не означава", result["note"])

    def test_non_html_response_is_not_accepted_as_a_page_check(self):
        response = FakeResponse("binary", content_type="application/octet-stream")
        with patch.object(check_official_sources.urllib.request, "urlopen", return_value=response):
            result = check_official_sources.check(self.source)
        self.assertEqual(result["status"], "error")
        self.assertIn("Content-Type", result["error"])

    def test_all_seven_sources_are_pending_until_the_new_monitor_runs(self):
        payload = json.loads((ROOT / "source_status.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["total"], 7)
        self.assertEqual(payload["ok"], 0)
        self.assertEqual(len({row["id"] for row in payload["sources"]}), 7)
        self.assertTrue(all(row["status"] == "pending_validation" for row in payload["sources"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
