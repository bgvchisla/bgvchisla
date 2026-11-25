#!/usr/bin/env python3
"""Offline regression tests for the debt and budget resource."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "dalg-i-byudzhet" / "index.html"
DATA = ROOT / "debt-budget.json"
FISCAL = ROOT / "official_fiscal.json"
SITEMAP = ROOT / "sitemap.xml"
HOMEPAGE = ROOT / "index.html"


class DebtBudgetResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))
        cls.fiscal = json.loads(FISCAL.read_text(encoding="utf-8"))
        cls.sitemap = SITEMAP.read_text(encoding="utf-8")
        cls.homepage = HOMEPAGE.read_text(encoding="utf-8")

    def test_page_has_search_metadata_schema_and_canonical_url(self):
        title = re.search(r"<title>(.*?)</title>", self.page, re.I | re.S)
        description = re.search(r'<meta name="description" content="([^"]+)"', self.page, re.I)
        self.assertIsNotNone(title)
        self.assertIsNotNone(description)
        self.assertLessEqual(len(title.group(1)), 60)
        self.assertLessEqual(len(description.group(1)), 160)
        self.assertIn('rel="canonical" href="https://bgvchisla.com/dalg-i-byudzhet/"', self.page)
        self.assertIn('type="application/ld+json"', self.page)
        self.assertIn('fetch("/debt-budget.json"', self.page)
        self.assertIn('fetch("/official_fiscal.json"', self.page)

    def test_resource_is_linked_from_homepage_and_sitemap(self):
        self.assertIn('href="/dalg-i-byudzhet/"', self.homepage)
        self.assertIn("<loc>https://bgvchisla.com/dalg-i-byudzhet/</loc>", self.sitemap)
        self.assertIn('href="/analizi/budget-2027/"', self.page)
        self.assertIn("Първични източници", self.page)

    def test_state_debt_and_central_government_subsector_are_distinct(self):
        latest = self.data["latest"]
        state = latest["state_debt"]
        subsector = latest["central_government_subsector_debt"]
        guaranteed = latest["guaranteed_debt"]
        self.assertEqual(state["nominal_mio_eur"], 35254.8)
        self.assertEqual(state["gdp_pct"], 27.0)
        self.assertEqual(subsector["nominal_mio_eur"], 37416.3)
        self.assertEqual(subsector["gdp_pct"], 28.7)
        self.assertGreater(subsector["nominal_mio_eur"], state["nominal_mio_eur"])
        self.assertEqual(guaranteed["nominal_mio_eur"], 746.8)
        self.assertIn("официалния регистър", self.data["definitions"]["state_debt"])
        self.assertIn("по-широк", self.data["definitions"]["central_subsector"])
        self.assertIn("условно", self.data["definitions"]["guaranteed"])

    def test_kfp_reported_values_reconcile_and_are_separate_from_october_estimate(self):
        latest = self.data["latest"]
        reported = latest["kfp_reported"]
        preliminary = latest["kfp_preliminary"]
        self.assertLessEqual(
            abs(reported["revenue_mio_eur"] - reported["expenditure_mio_eur"] - reported["balance_mio_eur"]),
            0.2,
        )
        self.assertEqual(reported["balance_mio_eur"], -3669.2)
        self.assertEqual(reported["interest_payments_kfp_mio_eur"], 974.5)
        self.assertEqual(preliminary["period"], "2026-10")
        self.assertEqual(preliminary["balance_mio_eur"], -5200.0)
        self.assertEqual(preliminary["balance_pct_forecast_gdp"], -4.0)
        self.assertIsNone(preliminary["revenue_mio_eur"])
        self.assertIn("Предварителна", preliminary["status"])

    def test_forecasts_keep_kfp_and_esa2010_series_separate(self):
        kfp = self.data["kfp_balance_forecast"]
        ministry = self.data["general_government_forecast"]["ministry"]
        commission = self.data["general_government_forecast"]["commission"]
        self.assertEqual([p["balance_pct_gdp"] for p in kfp], [-5.5, -3.5, -3.1, -2.4])
        self.assertEqual(ministry[0]["balance_pct_gdp"], -4.2)
        self.assertEqual(commission[1]["balance_pct_gdp"], -5.0)
        self.assertIn("не е идентично", self.data["definitions"]["kfp"])
        self.assertIn("ESA 2010", self.data["definitions"]["maastricht"])

    def test_historical_eurostat_series_and_forecasts_are_complete(self):
        history = self.data["maastricht_history"]
        forecast = self.data["state_debt_forecast"]
        self.assertEqual([p["year"] for p in history], [2022, 2023, 2024, 2025])
        self.assertEqual(history[-1]["debt_mio_eur"], 34797)
        self.assertEqual(history[-1]["deficit_mio_eur"], -4664)
        self.assertEqual([p["year"] for p in forecast], [2025, 2026, 2027, 2028, 2029])
        self.assertEqual(forecast[-1]["debt_bn_eur"], 56.7)
        self.assertEqual(forecast[-1]["debt_pct_gdp"], 35.5)

    def test_monthly_nsi_dataset_contains_the_six_required_series(self):
        ids = {row["id"] for row in self.fiscal["series"]}
        expected = {
            "central_government_balance",
            "central_government_revenue",
            "central_government_expenditure",
            "social_security_funds_balance",
            "social_security_funds_revenue",
            "social_security_funds_expenditure",
        }
        self.assertTrue(expected.issubset(ids))
        self.assertEqual(self.fiscal["latest_period"], "2026-09")
        self.assertIn("без натрупване", self.fiscal["methodology"])

    def test_sources_are_primary_https_urls(self):
        links = self.data["source_links"]
        self.assertGreaterEqual(len(links), 7)
        self.assertTrue(all(row["url"].startswith("https://") for row in links))
        self.assertTrue(any("minfin.bg" in row["url"] for row in links))
        self.assertTrue(any("nsi.bg" in row["url"] for row in links))
        self.assertTrue(any("ec.europa.eu" in row["url"] for row in links))


if __name__ == "__main__":
    unittest.main(verbosity=2)
