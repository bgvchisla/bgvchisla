#!/usr/bin/env python3
"""Offline regression tests for the NSI consumer-price importer."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_inflation as updater


def category_rows():
    rows = [
        ("00", "Общ ИПЦ", "101.2", "105.4", "106.0"),
        ("01", "Хранителни продукти и безалкохолни напитки", "100.6", "101.8", "102.0"),
        ("02", "Алкохолни напитки, тютюневи изделия", "101.1", "107.1", "107.5"),
        ("03", "Облекло и обувки", "107.4", "102.7", "100.3"),
        ("04", "Жилища, вода, електроенергия, газ и други горива", "100.3", "105.6", "105.6"),
        ("05", "Жилищно обзавеждане и услуги за дома", "100.4", "100.1", "100.1"),
        ("06", "Здравеопазване", "100.4", "102.9", "103.2"),
        ("07", "Транспорт", "100.0", "123.8", "126.2"),
        ("08", "Информация и комуникация", "100.4", "104.2", "101.9"),
        ("09", "Развлечения, спорт и култура", "107.0", "102.2", "109.1"),
        ("10", "Образователни услуги", "102.5", "109.1", "109.2"),
        ("11", "Услуги на ресторанти и хотели", "100.3", "108.8", "109.8"),
        ("12", "Застрахователни и финансови услуги", "100.7", "100.8", "101.9"),
        ("13", "Лични грижи и разни стоки и услуги", "100.4", "105.2", "105.3"),
    ]
    html_rows = []
    for code, name, mm, ytd, yoy in rows:
        html_rows.append(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in (code, name, mm, ytd, yoy)) + "</tr>"
        )
    return "<table><thead><tr><th>Код</th><th>Потребителски групи</th><th>м/м</th><th>YTD</th><th>г/г</th></tr></thead><tbody>" + "".join(html_rows) + "</tbody></table>"


def release_fixture():
    return """
    <!doctype html><html lang="bg"><head><title>НСИ</title></head><body>
    <h2>Индекс на потребителските цени (ИПЦ)</h2>
    <p>През октомври 2026 г. месечната инфлация е 1.2%, а годишната инфлация за октомври 2026 г. спрямо октомври 2025 г. е 6.0%.</p>
    <p>Инфлацията от началото на годината (октомври 2026 г. спрямо декември 2025 г.) е 5.4%.</p>
    <p>Средногодишната инфлация за периода ноември 2025 - октомври 2026 г. спрямо предходните 12 месеца е 5.1%.</p>
    <p>Натрупаната инфлация, измерена с ИПЦ, за последните три години (октомври 2026 г. спрямо октомври 2023 г.) е 13.7%, а за последните пет години (октомври 2026 г. спрямо октомври 2021 г.) е 41.5%.</p>
    <h2>Хармонизиран индекс на потребителските цени (ХИПЦ)</h2>
    <p>През октомври 2026 г. месечната инфлация е 0.7%, а годишната инфлация за октомври 2026 г. спрямо октомври 2025 г. е 5.9%.</p>
    <p>Инфлацията от началото на годината (октомври 2026 г. спрямо декември 2025 г.) е 5.6%.</p>
    <p>Средногодишната инфлация за периода ноември 2025 - октомври 2026 г. спрямо предходните 12 месеца е 4.4%.</p>
    <p>Натрупаната инфлация, измерена с ХИПЦ, за последните три години (октомври 2026 г. спрямо октомври 2023 г.) е 12.2%, а за последните пет години (октомври 2026 г. спрямо октомври 2021 г.) е 36.4%.</p>
    <h2>Индекс на цените за малката кошница (ИЦМК)</h2>
    <p>През октомври 2026 г. месечното изменение на индекса на цените на малката кошница е 0.7%, а годишното изменение за октомври 2026 г. спрямо октомври 2025 г. е 2.4%.</p>
    """ + category_rows() + """
    </body></html>
    """


class InflationImporterTests(unittest.TestCase):
    def test_discover_latest_release_excludes_flash_estimates(self):
        index = """
        <a href="/press-release/inflation-2026-09">Инфлация и индекси на потребителските цени - септември 2026 година</a>
        <a href="/press-release/inflation-2026-10-flash">Инфлация и индекси на потребителските цени - октомври 2026 година - експресна предварителна оценка</a>
        <a href="/press-release/inflation-2026-10">Инфлация и индекси на потребителските цени - октомври 2026 година</a>
        """
        period, url, label = updater.discover_latest_release(index)
        self.assertEqual(period, "2026-10")
        self.assertEqual(url, "https://www.nsi.bg/press-release/inflation-2026-10")
        self.assertNotIn("предварителна оценка", label.lower())

    def test_final_release_parses_all_indicators_and_thirteen_cpi_groups(self):
        payload = updater.parse_release(
            "2026-10",
            "https://www.nsi.bg/press-release/inflaciya-i-indeksi-na-potrebitelskite-ceni-9216",
            "Инфлация и индекси на потребителските цени - октомври 2026 година",
            release_fixture(),
            json.loads((ROOT / "inflation.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(payload["latest_period"], "2026-10")
        self.assertEqual(payload["latest_label"], "октомври 2026 г.")
        self.assertEqual(payload["latest"]["cpi"]["monthly"], 1.2)
        self.assertEqual(payload["latest"]["cpi"]["annual"], 6.0)
        self.assertEqual(payload["latest"]["cpi"]["ytd"], 5.4)
        self.assertEqual(payload["latest"]["cpi"]["annual_average"], 5.1)
        self.assertEqual(payload["latest"]["cpi"]["accumulated_3y"], 13.7)
        self.assertEqual(payload["latest"]["cpi"]["accumulated_5y"], 41.5)
        self.assertEqual(payload["latest"]["hicp"]["monthly"], 0.7)
        self.assertEqual(payload["latest"]["hicp"]["annual"], 5.9)
        self.assertEqual(payload["latest"]["hicp"]["ytd"], 5.6)
        self.assertEqual(payload["latest"]["hicp"]["annual_average"], 4.4)
        self.assertEqual(payload["latest"]["hicp"]["accumulated_3y"], 12.2)
        self.assertEqual(payload["latest"]["hicp"]["accumulated_5y"], 36.4)
        self.assertEqual(payload["latest"]["small_basket"], {"monthly": 0.7, "annual": 2.4})
        self.assertEqual(len(payload["cpi_categories"]), 13)
        food = next(row for row in payload["cpi_categories"] if row["code"] == "01")
        self.assertEqual(food["monthly_change"], 0.6)
        self.assertEqual(food["ytd_change"], 1.8)
        self.assertEqual(food["annual_change"], 2.0)
        self.assertEqual(payload["source_links"][0]["url"], payload["source_url"])

    def test_negative_numbers_and_bulgarian_month_names(self):
        self.assertEqual(updater.parse_number("минус 0,9"), -0.9)
        self.assertEqual(updater.parse_number("−0,5"), -0.5)
        self.assertEqual(updater.MONTHS_BG("2026-10"), "октомври 2026 г.")

    def test_category_extractor_ignores_total_row_and_converts_index_to_change(self):
        parser = updater.ReportParser()
        parser.feed(category_rows())
        rows = updater.extract_cpi_categories(parser.tables)
        self.assertEqual(len(rows), 13)
        self.assertTrue(all(row["code"] != "00" for row in rows))
        transport = next(row for row in rows if row["code"] == "07")
        self.assertEqual(transport["monthly_change"], 0.0)
        self.assertEqual(transport["ytd_change"], 23.8)
        self.assertEqual(transport["annual_change"], 26.2)

    def test_failed_download_does_not_overwrite_last_valid_file(self):
        original = '{"latest_period":"2026-10","sentinel":"keep"}\\n'
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "inflation.json"
            target.write_text(original, encoding="utf-8")
            with patch.object(updater, "OUTPUT", target), patch.object(
                updater, "fetch", side_effect=RuntimeError("source unavailable")
            ):
                with self.assertRaisesRegex(RuntimeError, "source unavailable"):
                    updater.main()
            self.assertEqual(target.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
