#!/usr/bin/env python3
"""Offline tests for the Employment Agency vacancy importer."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import ssl
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from update_labour_market import OUTPUT, build_ssl_context, main, parse_vacancy_snapshot


class VacancySnapshotTests(unittest.TestCase):
    def test_tls_context_uses_verified_tls12_and_ecdhe_only_suites(self):
        context = build_ssl_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)
        tls12 = [cipher for cipher in context.get_ciphers() if cipher["protocol"] == "TLSv1.2"]
        self.assertTrue(tls12)
        self.assertTrue(all("ECDHE" in cipher["name"] for cipher in tls12))

    def test_tls_transport_failure_keeps_last_valid_snapshot(self):
        previous = {
            "latest_period": "2026-Q3",
            "active_vacancies": {
                "as_of": "2026-11-27",
                "count": 6793,
                "source_url": "https://www.az.government.bg/bg/ejobs/view_prl/"
            },
            "last_updated": "2026-11-27T13:40:00Z"
        }
        original = json.dumps(previous, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "labour-market.json"
            target.write_text(original, encoding="utf-8")
            output = io.StringIO()
            with patch("update_labour_market.OUTPUT", target), patch(
                "update_labour_market.fetch",
                side_effect=urllib.error.URLError("TLS handshake failure")
            ), contextlib.redirect_stdout(output):
                main()
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("::warning::", output.getvalue())
            self.assertIn("6793", output.getvalue())
            self.assertIn("2026-11-27", output.getvalue())

    def test_parses_date_and_count_from_the_official_listing(self):
        page = """
        <html><body>
          <h1>Свободни работни места, обявени в бюрата по труда</h1>
          <p>Към <strong>27/11/2026</strong> в бюрата по труда има заявени
          <strong>6793</strong> свободни работни места.</p>
        </body></html>
        """
        result = parse_vacancy_snapshot(page)
        self.assertEqual(result["as_of"], "2026-11-27")
        self.assertEqual(result["count"], 6793)
        self.assertEqual(result["source_url"], "https://www.az.government.bg/bg/ejobs/view_prl/")

    def test_parses_space_grouped_vacancy_count(self):
        page = "<p>Към 03/12/2026 в бюрата по труда има заявени 7 125 свободни работни места.</p>"
        result = parse_vacancy_snapshot(page)
        self.assertEqual(result["as_of"], "2026-12-03")
        self.assertEqual(result["count"], 7125)

    def test_rejects_missing_or_undated_snapshot(self):
        with self.assertRaisesRegex(RuntimeError, "Не е открито"):
            parse_vacancy_snapshot("<p>Свободни работни места: 6793</p>")

    def test_rejects_invalid_calendar_date(self):
        page = "<p>Към 31/02/2026 в бюрата по труда има заявени 6793 свободни работни места.</p>"
        with self.assertRaisesRegex(RuntimeError, "Невалидна дата"):
            parse_vacancy_snapshot(page)

    def test_rejects_implausible_counts(self):
        page = "<p>Към 27/11/2026 в бюрата по труда има заявени 999999 свободни работни места.</p>"
        with self.assertRaisesRegex(RuntimeError, "Нереалистичен"):
            parse_vacancy_snapshot(page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
