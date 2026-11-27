#!/usr/bin/env python3
"""Offline regression tests for the Bulgarian labour-market resource."""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "labour-market.json"
PAGE = ROOT / "pazar-na-truda" / "index.html"


class LabourMarketDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_latest_labour_force_observations_are_q3_2026(self):
        l = self.data["labour_force"]
        self.assertEqual(self.data["latest_period"], "2026-Q3")
        self.assertEqual(l["period"], "2026-Q3")
        self.assertEqual(l["published_on"], "2026-11-13")
        self.assertEqual(l["total_employed_thousands"], 2927.8)
        self.assertEqual(l["unemployed_thousands"], 95.1)
        self.assertEqual(l["unemployment_rate_pct"], 3.1)
        self.assertEqual(l["employed_15_64_rate_pct"], 70.8)
        self.assertEqual(l["employment_20_64_rate_pct"], 77.0)
        self.assertEqual(l["activity_15_64_rate_pct"], 73.1)

    def test_q2_and_q3_series_keep_the_same_age_and_statistical_definitions(self):
        rows = self.data["labour_force_quarterly"]
        self.assertEqual([p["period"] for p in rows], ["2026-Q2", "2026-Q3"])
        self.assertEqual([p["unemployment_rate_pct"] for p in rows], [3.5, 3.1])
        self.assertEqual([p["employment_20_64_rate_pct"] for p in rows], [76.7, 77.0])
        self.assertEqual([p["activity_15_64_rate_pct"] for p in rows], [73.2, 73.1])
        self.assertEqual([p["youth_unemployment_15_29_pct"] for p in rows], [8.1, 8.1])

    def test_yoy_comparison_uses_the_same_quarter_of_the_previous_year(self):
        yoy = self.data["labour_force_yoy"]
        self.assertEqual(yoy["comparison_period"], "2025-Q3")
        self.assertEqual(yoy["current_period"], "2026-Q3")
        self.assertEqual(yoy["unemployment_rate_pct"]["previous"], 3.4)
        self.assertEqual(yoy["unemployment_rate_pct"]["current"], 3.1)
        self.assertEqual(yoy["employment_15_64_rate_pct"]["change_pp"], -0.6)
        self.assertEqual(yoy["employment_20_64_rate_pct"]["change_pp"], -0.5)

    def test_sector_employment_and_long_term_unemployment_reconcile(self):
        l = self.data["labour_force"]
        self.assertAlmostEqual(sum(x["employed_thousands"] for x in l["by_sector"]), 2927.8, delta=0.2)
        self.assertEqual(l["by_sector"][0]["share_pct"], 68.3)
        self.assertEqual(l["long_term_unemployed_thousands"], 41.5)
        self.assertEqual(l["long_term_unemployed_share_pct"], 43.6)
        self.assertEqual(l["long_term_unemployment_rate_pct"], 1.4)
        self.assertEqual(l["unemployed_15_29_rate_pct"], 8.1)

    def test_payroll_employees_are_not_conflated_with_all_employed_persons(self):
        p = self.data["payroll_employment"]
        l = self.data["labour_force"]
        self.assertEqual(p["employees_count"], 2324148)
        self.assertEqual(p["reference_date"], "2026-09-30")
        self.assertLess(p["employees_count"] / 1000, l["total_employed_thousands"])
        self.assertEqual([x["employees"] for x in p["monthly_series"]], [2367637, 2349339, 2324148])
        self.assertIn("по-тесен", p["note"])

    def test_wage_data_is_gross_monthly_and_has_three_months(self):
        w = self.data["wages"]
        self.assertEqual(w["period"], "2026-Q3")
        self.assertEqual(w["average_gross_monthly_eur"], 1438)
        self.assertEqual(w["qoq_change_pct"], -0.4)
        self.assertEqual(w["yoy_change_pct"], 10.4)
        self.assertEqual([x["gross_monthly_eur"] for x in w["monthly_series"]], [1445, 1411, 1458])
        self.assertEqual(w["public_sector_yoy_growth_pct"], 5.9)
        self.assertEqual(w["private_sector_yoy_growth_pct"], 11.9)
        self.assertIn("не медиана", w["methodology"])

    def test_wage_activity_extremes_and_september_table_are_complete(self):
        w = self.data["wages"]
        extremes = w["quarterly_activity_extremes"]
        self.assertEqual(len(extremes), 6)
        self.assertEqual(max(x["average_gross_monthly_eur"] for x in extremes if x["group"] == "highest"), 3059)
        self.assertEqual(min(x["average_gross_monthly_eur"] for x in extremes if x["group"] == "lowest"), 908)
        self.assertGreaterEqual(len(w["september_activity_wages"]), 18)
        ict = next(x for x in w["september_activity_wages"] if x["activity"].startswith("Създаване и разпространение на информация"))
        self.assertEqual(ict["gross_monthly_eur"], 3101)

    def test_registered_unemployment_and_open_vacancies_are_separate_administrative_indicators(self):
        az = self.data["az_registered"]
        vac = self.data["active_vacancies"]
        self.assertEqual(az["period"], "2026-10")
        self.assertEqual(az["registered_unemployed_count"], 158751)
        self.assertEqual(az["registered_unemployment_rate_pct"], 5.60)
        self.assertEqual(az["placed_in_jobs_with_agency_count"], 13085)
        self.assertEqual(az["employer_vacancies_primary_market_count"], 9213)
        self.assertEqual(vac["as_of"], "2026-11-27")
        self.assertEqual(vac["count"], 6793)
        self.assertIn("не е пряко съпоставим", self.data["methodology"]["registered_unemployment"])

    def test_productivity_uses_preliminary_national_accounts_and_is_not_lfs_employment(self):
        p = self.data["productivity"]
        self.assertEqual(p["period"], "2026-Q2")
        self.assertEqual(p["status"], "Предварителни данни")
        self.assertEqual(p["gdp_per_employed_current_eur"], 8272.6)
        self.assertEqual(p["gdp_per_hour_current_eur"], 21.2)
        self.assertEqual(p["gdp_per_employed_real_yoy_pct"], 3.1)
        self.assertEqual(p["gva_per_employed_real_yoy_pct"], 0.3)
        self.assertEqual(p["gva_per_hour_real_yoy_pct"], 0.5)
        self.assertEqual(p["employment_in_resident_production_units_thousands"], 3661.8)
        self.assertNotEqual(p["employment_in_resident_production_units_thousands"], self.data["labour_force"]["total_employed_thousands"])
        self.assertEqual(p["next_release_date"], "2026-12-04")
        self.assertIn("не съвпадат", p["methodology"])
        self.assertTrue(any("производителност" in x["title"].lower() for x in self.data["source_links"]))

    def test_labour_cost_index_is_separate_from_wage_growth(self):
        d = self.data["labour_cost_index"]
        self.assertEqual(d["period"], "2026-Q2")
        self.assertEqual(d["total_yoy_pct"], 9.9)
        self.assertEqual(d["industry_yoy_pct"], 12.2)
        self.assertEqual(d["services_yoy_pct"], 11.5)
        self.assertEqual(d["construction_yoy_pct"], 8.5)
        self.assertEqual(d["status"], "Предварителни данни")
        self.assertIn("не е равнозначно", d["note"])

    def test_page_metadata_and_dataset_loader_are_consistent(self):
        import re
        title = re.search(r"<title>(.*?)</title>", self.page, re.I | re.S)
        description = re.search(r'<meta name="description" content="([^"]+)"', self.page, re.I)
        self.assertIsNotNone(title)
        self.assertIsNotNone(description)
        self.assertLessEqual(len(title.group(1)), 60)
        self.assertLessEqual(len(description.group(1)), 160)
        self.assertIn('rel="canonical" href="https://bgvchisla.com/pazar-na-truda/"', self.page)
        self.assertIn('fetch("/labour-market.json"', self.page)
        self.assertGreaterEqual(len(self.data["source_links"]), 7)
        self.assertTrue(all(x["url"].startswith("https://") for x in self.data["source_links"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
