#!/usr/bin/env python3
"""Regression checks for verified, transparent editorial publication."""
from __future__ import annotations
import html, json, re, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/"analizi"/"index.html"
SITEMAP=ROOT/"sitemap.xml"
REGISTRY=ROOT/"analizi"/"articles.json"
GENERATOR_WORKFLOW=ROOT/".github"/"workflows"/"generate-analyses.yml"
AUDIT_WORKFLOW=ROOT/".github"/"workflows"/"audit-analysis-evidence.yml"
CONFIG=ROOT/"analysis"/"config.json"

class EditorialPublicationTests(unittest.TestCase):
    def test_every_registered_article_is_indexed_and_styled(self):
        articles=json.loads(REGISTRY.read_text(encoding="utf-8"))
        archive=ARCHIVE.read_text(encoding="utf-8")
        sitemap=SITEMAP.read_text(encoding="utf-8")
        self.assertTrue(articles)
        for item in articles:
            slug=str(item.get("slug",""))
            with self.subTest(slug=slug):
                self.assertRegex(slug,r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                urls=item.get("source_urls",[])
                self.assertGreaterEqual(len(urls),4)
                self.assertTrue(all(str(u).startswith("https://") for u in urls))
                page=(ROOT/"analizi"/slug/"index.html").read_text(encoding="utf-8")
                self.assertIn('<html lang="bg">',page) if 'data-ai-generated="true"' not in page else self.assertIn('data-ai-generated="true"',page)
                self.assertIn(f'<link rel="canonical" href="https://bgvchisla.com/analizi/{slug}/">',page)
                self.assertIn('property="og:title"',page)
                self.assertIn('property="og:description"',page)
                self.assertIn("--navy:#24384f",page)
                self.assertIn("--blue:#315f91",page)
                self.assertIn("@media(max-width:640px)",page)
                refs=set(re.findall(r'href="#source-(\d+)"',page))
                notes=set(re.findall(r'<li id="source-(\d+)"',page))
                self.assertTrue(refs and refs.issubset(notes))
                self.assertGreaterEqual(len(notes),4)
                self.assertIn(f'href="/analizi/{slug}/"',archive)
                self.assertIn(f"https://bgvchisla.com/analizi/{slug}/",sitemap)
                if 'data-ai-generated="true"' in page:
                    self.assertIn('class="ai-disclosure"',page)
                    body=re.search(r"<article>([\s\S]*?)</article>",page,re.I)
                    self.assertIsNotNone(body)
                    words=re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*",html.unescape(re.sub(r"<[^>]+>"," ",body.group(1))),re.UNICODE)
                    self.assertGreaterEqual(len(words),900)
                    self.assertLessEqual(len(words),1400)

    def test_weekly_schedule_and_lane_mapping(self):
        source=GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "0 7 * * 2"',source)
        self.assertIn('cron: "0 7 * * 5"',source)
        self.assertIn('"0 7 * * 2") LANE="bulgaria"',source)
        self.assertIn('"0 7 * * 5") LANE="world"',source)
        self.assertIn('MODE="publish"',source)

    def test_paid_publishing_is_closed_by_default_and_requires_two_keys(self):
        source=GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        for token in ("vars.ANALYSES_PUBLISH_ENABLED","secrets.OPENAI_API_KEY","secrets.GEMINI_API_KEY",
                      'PUBLISH_ENABLED" = "true"','OPENAI_KEY_PRESENT" = "true"','GEMINI_KEY_PRESENT" = "true"'):
            self.assertIn(token,source)
        self.assertNotIn("ANALYSES_AUTODRAFT_ENABLED",source)
        self.assertIn('default: "preflight"',source)

    def test_external_factcheck_is_a_mandatory_publication_gate(self):
        source=GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/fact_check_analysis.py",source)
        self.assertIn("analysis/factcheck_report.json",source)
        self.assertIn("steps.factcheck.outputs.verdict == 'PASS'",source)
        self.assertIn("Block publication unless the independent fact-check passes",source)
        self.assertLess(source.index("Run independent Gemini fact-check"),source.index("Merge only the audited commit"))
        self.assertLess(source.index("Require both API keys"),source.index("Generate the analysis with GPT-6 Luna"))
        self.assertNotIn("gh pr merge",source)
        self.assertNotIn("/approve",source)

    def test_ai_disclosure_is_added_before_validation(self):
        source=GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/apply_ai_disclosure.py",source)
        self.assertLess(source.index("Apply the visible AI transparency disclosure"),source.index("Validate the new article"))
        self.assertIn("analysis/verification_usage.json",source)

    def test_word_limit_and_budget_are_consistent(self):
        cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(cfg["minimum_words"],900)
        self.assertEqual(cfg["maximum_words"],1400)
        self.assertLessEqual(cfg["monthly_budget_usd"],3.5)
        self.assertEqual(cfg["monthly_total_budget_usd"],5.5)
        self.assertEqual(cfg["max_api_calls_per_month"],12)
        self.assertEqual(cfg["max_factcheck_calls_per_month"],12)
        self.assertEqual(cfg["review_model"],"gemini-3.8-flash")

    def test_manual_dispatch_defaults_to_preflight(self):
        source=GENERATOR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('default: "preflight"',source)
        self.assertIn("options: [preflight, publish]",source)
        self.assertIn("--dry-run",source)

    def test_audit_runs_every_pr_and_checks_factcheck_report(self):
        source=AUDIT_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/test_independent_factcheck.py --static",source)
        self.assertIn("scripts/test_independent_factcheck.py --report analysis/factcheck_report.json",source)
        self.assertIn("pull_request:",source)
        self.assertIn("branches: [main]",source)

if __name__=="__main__": unittest.main(verbosity=2)
