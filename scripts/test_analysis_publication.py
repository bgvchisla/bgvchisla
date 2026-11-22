#!/usr/bin/env python3
"""Regression checks for the editorial article and its approval/publication path."""
from __future__ import annotations

import html
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "analizi" / "budget-2027" / "index.html"
ARCHIVE = ROOT / "analizi" / "index.html"
SITEMAP = ROOT / "sitemap.xml"
REGISTRY = ROOT / "analizi" / "articles.json"
GENERATOR_WORKFLOW = ROOT / ".github" / "workflows" / "generate-analyses.yml"
APPROVAL_WORKFLOW = ROOT / ".github" / "workflows" / "approve-analysis.yml"


class EditorialPublicationTests(unittest.TestCase):
    @unittest.skipUnless(ARTICLE.exists(), "Article-specific check: skipped in pipeline-bootstrap PR.")
    def test_article_has_bulgarian_metadata_and_canonical_url(self):
        source = ARTICLE.read_text(encoding="utf-8")
        self.assertIn('<html lang="bg">', source)
        self.assertIn(
            '<link rel="canonical" href="https://bgvchisla.com/analizi/budget-2027/">',
            source,
        )
        self.assertIn("<h1>Бюджет 2027:", source)
        self.assertIn("22 ноември 2026 г.", source)
        self.assertNotIn("Първият анализ се подготвя", source)

    @unittest.skipUnless(ARTICLE.exists(), "Article-specific check: skipped in pipeline-bootstrap PR.")
    def test_every_inline_source_reference_resolves_to_a_source_note(self):
        source = ARTICLE.read_text(encoding="utf-8")
        references = set(re.findall(r'href="#source-(\d+)"', source))
        source_notes = set(re.findall(r'<li id="source-(\d+)"', source))
        self.assertGreaterEqual(len(source_notes), 10)
        self.assertTrue(references, "No inline source references found.")
        self.assertTrue(references.issubset(source_notes))
        for line in source.splitlines():
            if '<li id="source-' in line:
                self.assertIn('href="https://', line)

    @unittest.skipUnless(ARTICLE.exists(), "Article-specific check: skipped in pipeline-bootstrap PR.")
    def test_article_length_and_no_forbidden_dash_characters(self):
        source = ARTICLE.read_text(encoding="utf-8")
        for character in ("\u2012", "\u2013", "\u2014", "\u2015"):
            self.assertNotIn(character, source)
        match = re.search(r"<article>([\s\S]*?)</article>", source, flags=re.I)
        self.assertIsNotNone(match, "Article body not found.")
        body = html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
        words = re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", body, flags=re.UNICODE)
        self.assertGreaterEqual(len(words), 900)
        self.assertLessEqual(len(words), 1800)

    @unittest.skipUnless(ARTICLE.exists(), "Article-specific check: skipped in pipeline-bootstrap PR.")
    def test_archive_sitemap_and_source_registry_include_article(self):
        archive = ARCHIVE.read_text(encoding="utf-8")
        sitemap = SITEMAP.read_text(encoding="utf-8")
        articles = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertIn('href="/analizi/budget-2027/"', archive)
        self.assertIn("https://bgvchisla.com/analizi/budget-2027/", sitemap)
        matches = [item for item in articles if item.get("slug") == "budget-2027"]
        self.assertEqual(len(matches), 1)
        self.assertGreaterEqual(len(matches[0].get("source_urls", [])), 8)
        self.assertTrue(all(url.startswith("https://") for url in matches[0]["source_urls"]))

    def test_paid_generation_only_creates_review_pr_and_never_pushes_main(self):
        source = GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ANALYSES_AUTODRAFT_ENABLED", source)
        self.assertIn("options: [dry-run, draft]", source)
        self.assertIn("gh pr create", source)
        self.assertIn("gh workflow run audit-analysis-evidence.yml", source)
        self.assertNotIn("git push origin HEAD:main", source)
        self.assertIn("analysis/draft-", source)

    def test_owner_approval_requires_green_audit_and_dispatches_deployment(self):
        source = APPROVAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("issue_comment:", source)
        self.assertIn("github.event.comment.body == '/approve'", source)
        self.assertIn("github.actor == 'bgvchisla'", source)
        self.assertIn('BASE_REF', source)
        self.assertIn('HEAD_SHA', source)
        self.assertIn('AUDIT_RESULT', source)
        self.assertIn('sort_by(.time)', source)
        self.assertIn('CURRENT_HEAD_SHA', source)
        self.assertIn('gh api --method PUT', source)
        self.assertIn('sha="$HEAD_SHA"', source)
        self.assertNotIn('gh pr merge', source)
        self.assertIn('gh workflow run deploy-production.yml', source)

    def test_gpt_luna_budget_matches_the_approved_five_euro_cap(self):
        config = json.loads((ROOT / "analysis" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], "gpt-6-luna")
        self.assertEqual(config["monthly_budget_usd"], 5.5)
        self.assertEqual(config["max_api_calls_per_month"], 12)
        self.assertEqual(config["maximum_words"], 1800)


if __name__ == "__main__":
    unittest.main(verbosity=2)
