#!/usr/bin/env python3
"""Regression tests for publishing into the current site archive contract."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analysis_publishing import publish_article  # noqa: E402


class ModernPublishingTests(unittest.TestCase):
    def test_publishes_modern_page_registry_archive_and_sitemap_with_published_at(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analyses = root / "analizi"
            analyses.mkdir()
            (analyses / "today").mkdir()
            registry_path = analyses / "articles.json"
            archive_path = analyses / "index.html"
            sitemap_path = root / "sitemap.xml"

            legacy_row = {
                "slug": "budget-2027",
                "title": "Стар анализ",
                "published_at": "2026-11-22",
                "lane": "bulgaria",
                "source_urls": ["https://example.org/old-source"],
            }
            registry_path.write_text(json.dumps([legacy_row], ensure_ascii=False), encoding="utf-8")
            archive_path.write_text(
                '<!doctype html><html lang="bg"><body><main><div class="grid">'
                '<a class="article-card" href="/analizi/budget-2027/"><strong>Стар анализ</strong></a>'
                '</div></main></body></html>',
                encoding="utf-8",
            )
            sitemap_path.write_text(
                '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<url><loc>https://bgvchisla.com/analizi/</loc></url></urlset>',
                encoding="utf-8",
            )

            source_index = {
                f"N{i:02d}": {
                    "source_id": f"N{i:02d}",
                    "publisher": f"Източник {i}",
                    "title": f"Първичен документ {i}",
                    "url": f"https://example.org/source-{i}",
                }
                for i in range(1, 5)
            }
            article = {
                "title": "Българската икономика: проверка на тенденциите",
                "summary": "Анализ на публичните финанси, бизнеса и икономическите показатели.",
                "used_source_ids": ["N01", "N02", "N03", "N04"],
                "_src": source_index,
                "_words": 1020,
            }
            legacy_page = (
                '<!doctype html><html lang="bg"><head><meta charset="utf-8">'
                '<link rel="canonical" href="https://bgvchisla.com/analizi/legacy.html">'
                '<meta name="description" content="Кратко резюме"><style>body{margin:0}</style></head>'
                '<body><main><h1>Българската икономика</h1>'
                '<div class="meta">Редакция БЪЛГАРИЯ В ЧИСЛА / 24.11.2026 / 1020 думи</div>'
                '<article><section><h2>Основни тенденции</h2><p>Съдържание с проверими доказателства.</p></section></article>'
                '<div class="sources"><h2>Източници</h2><ol>'
                '<li><a href="https://example.org/source-1">Източник 1</a></li>'
                '<li><a href="https://example.org/source-2">Източник 2</a></li>'
                '<li><a href="https://example.org/source-3">Източник 3</a></li>'
                '<li><a href="https://example.org/source-4">Източник 4</a></li>'
                '</ol></div></main></body></html>'
            )

            page_path = publish_article(
                root=root,
                article=article,
                lane="bulgaria",
                now=datetime(2026, 11, 24, 10, 30, tzinfo=timezone.utc),
                date_label="24.11.2026",
                rendered_page=legacy_page,
                slug="2026-11-24-bulgarskata-ikonomika",
            )

            self.assertEqual(
                page_path,
                analyses / "2026-11-24-bulgarskata-ikonomika" / "index.html",
            )
            self.assertTrue(page_path.is_file())
            page = page_path.read_text(encoding="utf-8")
            for token in (
                '<html lang="bg">',
                '<link rel="canonical" href="https://bgvchisla.com/analizi/2026-11-24-bulgarskata-ikonomika/">',
                'property="og:title"',
                'property="og:description"',
                '<div class="byline">',
                "--navy:#24384f",
                "--blue:#315f91",
                "--risk:#b64b45",
                "@media(max-width:640px)",
                "<article>",
                '<ol class="source-list">',
            ):
                self.assertIn(token, page)

            rows = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["slug"], "2026-11-24-bulgarskata-ikonomika")
            self.assertEqual(rows[0]["published_at"], "2026-11-24")
            self.assertEqual(rows[0]["lane"], "bulgaria")
            self.assertEqual(len(rows[0]["source_urls"]), 4)
            self.assertEqual(rows[1], legacy_row)
            self.assertNotIn("date", rows[0])

            archive = archive_path.read_text(encoding="utf-8")
            self.assertIn('href="/analizi/2026-11-24-bulgarskata-ikonomika/"', archive)
            self.assertLess(archive.index('href="/analizi/2026-11-24-bulgarskata-ikonomika/"'),
                            archive.index('href="/analizi/budget-2027/"'))

            sitemap = sitemap_path.read_text(encoding="utf-8")
            self.assertIn(
                "https://bgvchisla.com/analizi/2026-11-24-bulgarskata-ikonomika/",
                sitemap,
            )

    def test_refuses_fewer_than_four_distinct_primary_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "analizi").mkdir()
            (root / "analizi" / "articles.json").write_text("[]", encoding="utf-8")
            (root / "analizi" / "index.html").write_text('<div class="grid"></div>', encoding="utf-8")
            (root / "sitemap.xml").write_text("<urlset></urlset>", encoding="utf-8")
            article = {
                "title": "Тест",
                "summary": "Тест",
                "used_source_ids": ["N01", "N02", "N03"],
                "_src": {
                    sid: {"url": f"https://example.org/{sid}"}
                    for sid in ("N01", "N02", "N03")
                },
            }
            with self.assertRaisesRegex(RuntimeError, "поне четири"):
                publish_article(
                    root, article, "bulgaria",
                    datetime(2026, 11, 24, tzinfo=timezone.utc),
                    "24.11.2026",
                    '<html lang="bg"><head><link rel="canonical" href="https://example.org"></head>'
                    '<style></style><div class="meta">Редакция БЪЛГАРИЯ В ЧИСЛА / дата</div>'
                    '<article></article></html>',
                    "test-article",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
