#!/usr/bin/env python3
"""Regression tests for strict evidence selection and dead-link filtering."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analysis_evidence


DEAD_URL = (
    "https://www.economic.bg/bg/a/view/"
    "upravljavashtite-poshtadiha-malkite-tyrgovci-ot-novija-danyk-svryhpechalba"
)


class PermanentDeadLinkTests(unittest.TestCase):
    def setUp(self):
        analysis_evidence._URL_STATUS_CACHE.clear()

    def test_404_is_treated_as_permanently_unavailable_using_ranged_get(self):
        seen = {}

        def respond(request, timeout):
            seen["method"] = request.get_method()
            seen["range"] = request.get_header("Range")
            raise HTTPError(request.full_url, 404, "Not Found", None, None)

        with patch.object(analysis_evidence.urllib.request, "urlopen", side_effect=respond):
            self.assertTrue(analysis_evidence._is_permanently_unavailable(DEAD_URL))

        self.assertEqual(seen["method"], "GET")
        self.assertEqual(seen["range"], "bytes=0-0")

    def test_410_is_treated_as_permanently_unavailable(self):
        error = HTTPError(DEAD_URL, 410, "Gone", None, None)
        with patch.object(analysis_evidence.urllib.request, "urlopen", side_effect=error):
            self.assertTrue(analysis_evidence._is_permanently_unavailable(DEAD_URL))

    def test_403_is_not_assumed_to_be_a_dead_link(self):
        error = HTTPError(DEAD_URL, 403, "Forbidden", None, None)
        with patch.object(analysis_evidence.urllib.request, "urlopen", side_effect=error):
            self.assertFalse(analysis_evidence._is_permanently_unavailable(DEAD_URL))

    def test_temporary_network_error_fails_open(self):
        with patch.object(
            analysis_evidence.urllib.request,
            "urlopen",
            side_effect=URLError("temporary network error"),
        ):
            self.assertFalse(analysis_evidence._is_permanently_unavailable(DEAD_URL))

    def test_dead_link_result_is_cached(self):
        error = HTTPError(DEAD_URL, 404, "Not Found", None, None)
        with patch.object(
            analysis_evidence.urllib.request,
            "urlopen",
            side_effect=error,
        ) as urlopen:
            self.assertTrue(analysis_evidence._is_permanently_unavailable(DEAD_URL))
            self.assertTrue(analysis_evidence._is_permanently_unavailable(DEAD_URL))
            self.assertEqual(urlopen.call_count, 1)


class BulgarianEvidenceSelectionTests(unittest.TestCase):
    def test_confirmed_404_is_skipped_without_weakening_editorial_minimums(self):
        analysis_evidence._URL_STATUS_CACHE.clear()

        def is_dead(url):
            return url == DEAD_URL

        with patch.object(analysis_evidence, "_is_permanently_unavailable", side_effect=is_dead):
            pack = analysis_evidence.get_evidence("bulgaria")

        news_sources = [
            source for source in pack["sources"]
            if str(source.get("source_id", "")).startswith("N")
        ]
        self.assertNotIn(DEAD_URL, {source["url"] for source in news_sources})
        self.assertGreaterEqual(len(news_sources), 4)

        domestic = [
            source for source in news_sources
            if source.get("editorial_role") == "Български икономически материал"
        ]
        context = [
            source for source in news_sources
            if str(source.get("editorial_role", "")).startswith("Международен контекст за България:")
        ]
        publishers = {source["publisher"] for source in news_sources}
        self.assertGreaterEqual(len(domestic), 2)
        self.assertGreaterEqual(len(context), 1)
        self.assertGreaterEqual(len(publishers), 2)
        self.assertGreaterEqual(len(pack["sources"]), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
