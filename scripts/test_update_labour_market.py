#!/usr/bin/env python3
"""Offline tests for the Employment Agency vacancy importer."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from update_labour_market import parse_vacancy_snapshot


class VacancySnapshotTests(unittest.TestCase):
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
        self.assertEqual(result["source_url"], "https://az.government.bg/bg/ejobs/view_prl/")

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
