#!/usr/bin/env python3
"""Offline validation for the official BNB banking resource."""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "banking.json"
BNB_MONTHLY = ROOT / "official_bnb.json"
PAGE = ROOT / "banki" / "index.html"


class BankingDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))
        cls.monthly = json.loads(BNB_MONTHLY.read_text(encoding="utf-8"))
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_quarterly_loan_sector_components_reconcile(self):
        q = self.data["sector_quarterly"]
        self.assertEqual(q["points_periods"], ["2025-09", "2025-12", "2026-03", "2026-06", "2026-09"])
        for i, period in enumerate(q["points_periods"]):
            total = sum(q["loans"][key][i]["value"] for key in (
                "nonfinancial_enterprises", "financial_enterprises", "households_npish"
            ))
            self.assertAlmostEqual(total, q["loans"]["total"][i]["value"], delta=0.001, msg=period)
            for series in q["loans"].values():
                self.assertEqual(series[i]["period"], period)
                self.assertGreater(series[i]["value"], 0)

    def test_quarterly_deposit_sector_components_reconcile(self):
        q = self.data["sector_quarterly"]
        for i, period in enumerate(q["points_periods"]):
            total = sum(q["deposits"][key][i]["value"] for key in (
                "nonfinancial_enterprises", "financial_enterprises", "households_npish"
            ))
            self.assertAlmostEqual(total, q["deposits"]["total"][i]["value"], delta=0.002, msg=period)  # BNB table values are rounded to thousand EUR.
            for series in q["deposits"].values():
                self.assertEqual(series[i]["period"], period)
                self.assertGreater(series[i]["value"], 0)

    def test_monetary_and_balance_sheet_scopes_are_kept_separate(self):
        m = self.data["monetary_statistics"]
        b = self.data["banking_system"]
        self.assertEqual(m["non_government_loans_mio_eur"], 67693)
        self.assertEqual(m["non_government_deposits_mio_eur"], 87590)
        self.assertEqual(b["gross_loans_advances_bn_eur"], 83.8)
        self.assertEqual(b["deposits_bn_eur"], 103.6)
        self.assertIn("не са взаимозаменяеми", m["note"])
        self.assertIn("различава", self.data["methodology"]["banking_system"])

    def test_latest_credit_and_deposit_growth_matches_the_published_sector_snapshot(self):
        q = self.data["sector_quarterly"]
        self.assertEqual(q["loans"]["nonfinancial_enterprises"][-1]["value"], 29647.216)
        self.assertEqual(q["loans"]["financial_enterprises"][-1]["value"], 5256.605)
        self.assertEqual(q["loans"]["households_npish"][-1]["value"], 33115.495)
        self.assertEqual(q["loans"]["total"][-1]["value"], 68019.316)
        self.assertEqual(q["deposits"]["nonfinancial_enterprises"][-1]["value"], 27958.958)
        self.assertEqual(q["deposits"]["financial_enterprises"][-1]["value"], 2409.926)
        self.assertEqual(q["deposits"]["households_npish"][-1]["value"], 57221.514)
        self.assertEqual(q["deposits"]["total"][-1]["value"], 87590.398)
        self.assertEqual(q["annual_growth_pct"]["loans"]["households_npish"], 20.7)
        self.assertEqual(q["annual_growth_pct"]["deposits"]["households_npish"], 16.2)

    def test_supervisory_asset_quality_and_liquidity_metrics_have_reference_period(self):
        b = self.data["banking_system"]
        self.assertEqual(b["reference_date"], "2026-09-30")
        self.assertEqual(b["assets_bn_eur"], 124.4)
        self.assertEqual(b["npl_gross_bn_eur"], 2.2)
        self.assertEqual(b["npl_gross_ratio_pct"], 2.59)
        self.assertEqual(b["npl_net_ratio_pct"], 1.24)
        self.assertEqual(b["liquidity_coverage_ratio_pct"], 263.1)
        self.assertEqual(b["profit_bn_eur"], 1.6)
        self.assertEqual(b["impairment_costs_mio_eur"], 382)

    def test_interest_rates_distinguish_new_business_and_apr(self):
        r = self.data["interest_rates"]
        self.assertEqual(r["period"], "2026-09")
        self.assertEqual(r["household"]["housing_loan_rate_pct"], 2.41)
        self.assertEqual(r["household"]["housing_apr_pct"], 2.76)
        self.assertEqual(r["household"]["consumer_loan_rate_pct"], 8.83)
        self.assertEqual(r["household"]["consumer_apr_pct"], 9.11)
        self.assertEqual(r["nonfinancial_enterprises"]["loan_rate_up_to_1m_eur_pct"], 4.25)
        self.assertEqual(r["nonfinancial_enterprises"]["loan_rate_above_1m_eur_pct"], 4.66)
        self.assertIn("ГПР включва", self.data["methodology"]["interest"])

    def test_capital_ratios_are_not_mislabeled_as_september_2026(self):
        c = self.data["capital_adequacy"]
        self.assertEqual(c["reference_date"], "2025-12-31")
        self.assertEqual(c["cet1_ratio_pct"], 24.89)
        self.assertEqual(c["tier1_ratio_pct"], 25.14)
        self.assertEqual(c["total_capital_ratio_pct"], 26.56)
        self.assertEqual(c["leverage_ratio_pct"], 11.26)
        self.assertEqual(c["net_stable_funding_ratio_pct"], 167.0)
        self.assertIn("не се представят", c["note"].lower())

    def test_monthly_household_loan_dataset_is_present_and_current(self):
        d = self.monthly
        latest = d["latest_period"]
        for key in ("household_consumer_loans", "household_housing_loans", "household_other_loans"):
            points = d["series"][key]["points"]
            self.assertGreaterEqual(len(points), 237)
            self.assertEqual(points[-1]["period"], latest)
            self.assertTrue(all(math.isfinite(p["value"]) and p["value"] >= 0 for p in points))
        self.assertIn("не представляват общия кредитен портфейл", d["methodology"])

    def test_primary_sources_are_official_and_page_loads_both_data_files(self):
        links = self.data["source_links"]
        self.assertGreaterEqual(len(links), 8)
        self.assertTrue(all(link["url"].startswith("https://") for link in links))
        self.assertTrue(all("bnb" in link["url"].lower() for link in links))
        self.assertIn('fetch("/banking.json"', self.page)
        self.assertIn('fetch("/official_bnb.json"', self.page)
        self.assertIn('rel="canonical" href="https://bgvchisla.com/banki/"', self.page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
