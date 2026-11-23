#!/usr/bin/env python3
"""Static and report-integrity tests for independent direct-URL fact checking."""
from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fact_check_analysis import extract_numeric_statements
CONFIG = ROOT / "analysis" / "config.json"
WORKFLOW = ROOT / ".github" / "workflows" / "generate-analyses.yml"
VERIFIER = ROOT / "scripts" / "fact_check_analysis.py"
DISCLOSURE = ROOT / "scripts" / "apply_ai_disclosure.py"




class NumericExtractionTests(unittest.TestCase):
    def test_nested_kpi_and_chart_values_are_in_numeric_audit(self):
        page = """<!doctype html><html lang="bg"><body>
        <main>
          <div class="metric"><strong>4,2%</strong><span>Дефицит за 2027 г.</span></div>
          <article>
            <p>Растежът на БВП е 2,5% през 2026 г.</p>
            <div class="chart"><div class="bars">
              <div class="bar-row"><span>2025</span>
                <div class="bar-track"><div class="bar-fill" style="width:36%"></div></div>
                <span class="bar-value">908 млн.</span>
              </div>
            </div></div>
            <div class="table-wrap"><table><tr><td>2027</td><td>3,5%</td></tr></table></div>
          </article>
        </main></body></html>"""
        statements = extract_numeric_statements(page)
        joined = " | ".join(item["statement"] for item in statements)
        self.assertIn("4,2%", joined)
        self.assertIn("2,5%", joined)
        self.assertIn("2025", joined)
        self.assertIn("908 млн.", joined)
        self.assertIn("3,5%", joined)


def validate_report(path: Path) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report.get("overall_verdict") == "PASS", "Независимият fact-check не е PASS."
    assert report.get("review_provider") == "Google"
    assert report.get("review_model") == "gemini-3.8-flash"
    assert report.get("review_method") == (
        "Gemini API URL Context; direct retrieval of cited primary-source URLs; no Google Search grounding"
    )
    assert int(report.get("verified_claims", 0)) >= 8
    assert int(report.get("retrieved_source_count", 0)) >= 4
    assert int(report.get("official_retrieved_domain_count", 0)) >= 2
    assert int(report.get("numeric_blocks_found", 0)) > 0
    assert report.get("numeric_blocks_verified") == report.get("numeric_blocks_found")
    assert not report.get("retrieval_failures")
    assert not report.get("blocking_reasons")

    retrieved = set(report.get("retrieved_sources", []))
    claims = report.get("claims_checked", [])
    assert len(claims) >= 8
    for claim in claims:
        assert claim.get("verdict") == "verified"
        evidence = set(claim.get("evidence_urls", []))
        assert evidence and evidence.issubset(retrieved), "Твърдението няма доказателство от извлечен първичен URL."

    numeric_items = report.get("numeric_audit_items", [])
    assert len(numeric_items) == report.get("numeric_blocks_found")
    for item in numeric_items:
        assert item.get("verdict") == "verified"
        assert item.get("statement"), "Липсва точният числов блок, върнат от проверяващия."
        evidence = set(item.get("evidence_urls", []))
        assert evidence and evidence.issubset(retrieved)


def validate_static() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    workflow = WORKFLOW.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    disclosure = DISCLOSURE.read_text(encoding="utf-8")

    assert config["review_provider"] == "Google"
    assert config["review_model"] == "gemini-3.8-flash"
    assert config["minimum_words"] == 900 and config["maximum_words"] == 1400
    assert config["monthly_total_budget_usd"] == 5.5
    assert config["max_factcheck_calls_per_month"] == 10
    assert config["minimum_retrieved_sources"] >= 4
    assert config["minimum_official_retrieved_domains"] >= 2
    assert config["maximum_source_urls_per_call"] <= 20
    assert config["maximum_review_input_tokens"] == 70000
    assert config["maximum_review_output_tokens"] == 5000
    assert len(config["official_source_domains"]) >= 10

    assert "automation/fix-chart-numeric-" in (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
        assert "fix/debt-counter-" in (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
    assert "ANALYSES_PUBLISH_ENABLED" in workflow
    assert "GEMINI_API_KEY" in workflow and "OPENAI_API_KEY" in workflow
    assert "steps.factcheck.outputs.verdict == 'PASS'" in workflow
    assert "fact_check_analysis.py" in workflow and "apply_ai_disclosure.py" in workflow
    assert "URL Context" in workflow
    assert '"google_search"' not in workflow

    assert '"url_context": {}' in verifier
    assert "urlContextMetadata" in verifier
    assert "URL_RETRIEVAL_STATUS_SUCCESS" in verifier
    assert "numeric_statements" in verifier
    assert "normalized_quote" in verifier
    assert "quote_matches_article" in verifier
    assert "statement_matches" in verifier
    assert "numeric_audit_items" in verifier
    assert "toolUsePromptTokenCount" in verifier
    assert "thoughtsTokenCount" in verifier
    assert "thinkingConfig" in verifier and "thinkingLevel" in verifier
    assert '"google_search"' not in verifier and '"googleSearch"' not in verifier
    assert "ANALYSES_PUBLISH_ENABLED" in verifier
    assert "official_source_domains" in verifier and "is_official_domain" in verifier
    assert "retrieved_sources" in verifier
    assert "URL Context" in disclosure
    assert "Не е преминал човешка редакционна проверка" in disclosure
    assert "Google Search" not in disclosure
    assert "ANALYSES_AUTODRAFT_ENABLED" not in workflow
    assert "/approve" not in workflow
    print("Статичните проверки за независима проверка чрез директни първични URL адреси са успешни.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    if args.static:
        validate_static()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NumericExtractionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.report:
        validate_report(Path(args.report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
