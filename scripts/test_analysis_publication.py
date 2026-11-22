#!/usr/bin/env python3
"""Regression checks for autonomous, verified editorial publication."""
from __future__ import annotations

import html
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "analizi" / "index.html"
SITEMAP = ROOT / "sitemap.xml"
REGISTRY = ROOT / "analizi" / "articles.json"
GENERATOR_WORKFLOW = ROOT / ".github" / "workflows" / "generate-analyses.yml"
APPROVAL_WORKFLOW = ROOT / ".github" / "workflows" / "approve-analysis.yml"
AUDIT_WORKFLOW = ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml"
CONFIG = ROOT / "analysis" / "config.json"


class EditorialPublicationTests(unittest.TestCase):
    def test_every_registered_article_is_complete_indexed_and_styled(self):
        articles = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertTrue(articles)
        archive = ARCHIVE.read_text(encoding="utf-8")
        sitemap = SITEMAP.read_text(encoding="utf-8")
        seen = set()
        for item in articles:
            slug = str(item.get("slug", ""))
            with self.subTest(slug=slug):
                self.assertRegex(slug, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertNotIn(slug, seen)
                seen.add(slug)
                self.assertTrue(str(item.get("title", "")).strip())
                self.assertIn(item.get("lane"), {"bulgaria", "world"})
                urls = item.get("source_urls", [])
                self.assertGreaterEqual(len(urls), 4)
                self.assertTrue(all(str(url).startswith("https://") for url in urls))
                path = ROOT / "analizi" / slug / "index.html"
                self.assertTrue(path.is_file(), f"Missing page: {path}")
                source = path.read_text(encoding="utf-8")
                self.assertIn('<html lang="bg">', source)
                self.assertIn(f'<link rel="canonical" href="https://bgvchisla.com/analizi/{slug}/">', source)
                self.assertIn('property="og:title"', source)
                self.assertIn('property="og:description"', source)
                self.assertIn("<h1>", source)
                self.assertIn("<article>", source)
                for token in ("--navy:#24384f", "--blue:#315f91", "--risk:#b64b45", "@media(max-width:640px)"):
                    self.assertIn(token, source)
                match = re.search(r"<article>([\s\S]*?)</article>", source, flags=re.I)
                self.assertIsNotNone(match)
                body = html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
                words = re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", body, flags=re.UNICODE)
                self.assertGreaterEqual(len(words), 900)
                self.assertLessEqual(len(words), 1800)
                refs = set(re.findall(r'href="#source-(\d+)"', source))
                notes = set(re.findall(r'<li id="source-(\d+)"', source))
                self.assertTrue(refs)
                self.assertTrue(refs.issubset(notes))
                self.assertGreaterEqual(len(notes), 4)
                for line in source.splitlines():
                    if '<li id="source-' in line:
                        self.assertIn('href="https://', line)
                for char in ("\u2012", "\u2013", "\u2014", "\u2015"):
                    self.assertNotIn(char, source)
                self.assertIn(f'href="/analizi/{slug}/"', archive)
                self.assertIn(f"https://bgvchisla.com/analizi/{slug}/", sitemap)

    def test_weekly_schedule_runs_twice_and_maps_the_correct_focus(self):
        source = GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "0 7 * * 2"', source)
        self.assertIn('cron: "0 7 * * 5"', source)
        self.assertIn('"0 7 * * 2") LANE="bulgaria"', source)
        self.assertIn('"0 7 * * 5") LANE="world"', source)
        self.assertIn('MODE="publish"', source)

    def test_publication_is_fully_automated_after_machine_validation(self):
        source = GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "OPENAI_API_KEY",
            "gh pr create",
            "gh workflow run audit-analysis-evidence.yml",
            "select(.name == \"audit\")",
            "context=editorial-approval",
            "gh api --method PUT",
            'sha="$EXPECTED_SHA"',
            "merge_method=squash",
            "gh workflow run deploy-production.yml",
            "Wait for successful Cloudflare Pages deployment",
            "GITHUB_STEP_SUMMARY",
        ):
            self.assertIn(token, source)
        self.assertNotIn("ANALYSES_AUTODRAFT_ENABLED", source)
        self.assertNotIn("/approve", source)
        self.assertNotIn("gh pr merge", source)
        self.assertFalse(APPROVAL_WORKFLOW.exists())

    def test_manual_dispatch_defaults_to_free_preflight(self):
        source = GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('default: "preflight"', source)
        self.assertIn("options: [preflight, publish]", source)
        self.assertIn("--dry-run", source)
        self.assertIn("if: steps.plan.outputs.mode == 'publish'", source)

    def test_gpt_luna_spending_guard_matches_five_euro_monthly_cap(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(config["model"], "gpt-6-luna")
        self.assertLessEqual(config["monthly_budget_usd"], 5.5)
        self.assertGreater(config["monthly_budget_usd"], 0)
        self.assertEqual(config["max_api_calls_per_month"], 12)
        self.assertEqual(config["max_output_tokens"], 5500)
        self.assertEqual(config["minimum_words"], 900)
        self.assertEqual(config["maximum_words"], 1800)

    def test_independent_audit_runs_on_every_pull_request_to_main(self):
        source = AUDIT_WORKFLOW.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  pull_request:\n(.*?)(?=^\S|\Z)", source)
        self.assertIsNotNone(match)
        self.assertIn("branches: [main]", match.group(1))
        self.assertNotIn("paths:", match.group(1))

    def test_audit_runs_frontend_source_and_both_lane_checks(self):
        source = AUDIT_WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "scripts/test_analysis_publication.py",
            "scripts/test_frontend.py",
            "scripts/test_responsive.mjs",
            "scripts/analysis_evidence.py --lane bulgaria",
            "scripts/analysis_evidence.py --lane world",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
