#!/usr/bin/env python3
"""Static and report-integrity tests for independent direct-URL fact checking."""
from __future__ import annotations

import argparse
import json
import sys
import unittest
import datetime as dt
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fact_check_analysis import (
    accumulate_usage_totals, calculate_billable_usage, evidence_urls_are_retrieved,
    extract_numeric_statements, extract_retrieval_metadata, normalized_domain,
    parse_json_response, response_diagnostics, reserve_budget, build_prompt,
)
CONFIG = ROOT / "analysis" / "config.json"
MANUAL_WORKFLOW = ROOT / ".github" / "workflows" / "verify-manual-analysis.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "generate-analyses.yml"
VERIFIER = ROOT / "scripts" / "fact_check_analysis.py"
DISCLOSURE = ROOT / "scripts" / "apply_ai_disclosure.py"




class VerifierResponseParsingTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "overall_verdict": "REVIEW",
            "summary": "Тестов резултат",
            "claims_checked": [],
            "numerical_audit": {"items": [], "issues": []},
            "methodology_issues": [],
            "limitations": [],
        }

    def payload(self, parts, finish_reason="STOP", usage=None):
        return {
            "candidates": [{
                "finishReason": finish_reason,
                "content": {"role": "model", "parts": parts},
                "safetyRatings": [],
            }],
            "usageMetadata": usage or {"promptTokenCount": 12, "candidatesTokenCount": 30},
        }

    def test_internal_thought_parts_are_not_parsed_as_final_answer(self):
        payload = self.payload([
            {"text": "internal reasoning, not JSON", "thought": True},
            {"text": json.dumps(self.report, ensure_ascii=False)},
        ])
        self.assertEqual(parse_json_response(payload), self.report)

    def test_parser_accepts_json_with_a_text_prefix(self):
        payload = self.payload([
            {"text": "Проверка на данните:\n" + json.dumps(self.report, ensure_ascii=False)}
        ])
        self.assertEqual(parse_json_response(payload), self.report)

    def test_parser_rejects_non_stop_finish_reason(self):
        payload = self.payload([{"text": "{\"overall_verdict\":"}], finish_reason="MAX_TOKENS")
        with self.assertRaisesRegex(ValueError, "MAX_TOKENS"):
            parse_json_response(payload)

    def test_parser_rejects_truncated_json_without_exposing_content(self):
        payload = self.payload([{"text": "{\"overall_verdict\":\"PASS\""}])
        with self.assertRaisesRegex(ValueError, "incomplete or invalid JSON"):
            parse_json_response(payload)
        diagnostics = response_diagnostics(payload)
        safe = json.dumps(diagnostics, ensure_ascii=False)
        self.assertEqual(diagnostics["candidate_count"], 1)
        self.assertEqual(diagnostics["finish_reason"], "STOP")
        self.assertEqual(diagnostics["final_text_characters"], 25)
        self.assertNotIn("overall_verdict", safe)
        self.assertEqual(diagnostics["usage_metadata"]["promptTokenCount"], 12)

    def test_parser_rejects_incomplete_schema(self):
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            parse_json_response(self.payload([{"text": "{\"overall_verdict\":\"PASS\"}"}]))

    def test_diagnostics_distinguish_thought_and_final_parts(self):
        payload = self.payload([
            {"text": "hidden", "thought": True},
            {"text": "{\"x\":1}"},
        ])
        diagnostics = response_diagnostics(payload)
        self.assertEqual(diagnostics["thought_text_part_count"], 1)
        self.assertEqual(diagnostics["final_text_part_count"], 1)
        self.assertEqual(diagnostics["final_text_characters"], 7)


class BillingAccountingTests(unittest.TestCase):
    def test_thinking_and_tool_tokens_are_included_in_billable_cost(self):
        usage = {
            "promptTokenCount": 100,
            "toolUsePromptTokenCount": 40,
            "candidatesTokenCount": 200,
            "thoughtsTokenCount": 60,
            "totalTokenCount": 400,
        }
        result = calculate_billable_usage(
            usage,
            input_price=0.75,
            output_price=1.875,
            fallback_cost=0.02,
        )
        self.assertEqual(result["billed_input_tokens"], 140)
        self.assertEqual(result["billed_output_tokens"], 260)
        self.assertEqual(result["prompt_tokens"], 100)
        self.assertEqual(result["tool_input_tokens"], 40)
        self.assertEqual(result["candidate_output_tokens"], 200)
        self.assertEqual(result["thinking_output_tokens"], 60)
        self.assertEqual(result["actual_cost_usd"], 0.0005925)

    def test_missing_thinking_metadata_defaults_to_zero_without_overcharging(self):
        result = calculate_billable_usage(
            {"promptTokenCount": 100, "toolUsePromptTokenCount": 20, "candidatesTokenCount": 80},
            input_price=0.75,
            output_price=1.875,
            fallback_cost=0.02,
        )
        self.assertEqual(result["billed_input_tokens"], 120)
        self.assertEqual(result["billed_output_tokens"], 80)
        self.assertEqual(result["thinking_output_tokens"], 0)
        self.assertEqual(result["actual_cost_usd"], 0.00024)

    def test_empty_usage_metadata_uses_reserved_cost_fallback(self):
        result = calculate_billable_usage({}, 0.75, 1.875, fallback_cost=0.01234567)
        self.assertEqual(result["billed_input_tokens"], 0)
        self.assertEqual(result["billed_output_tokens"], 0)
        self.assertEqual(result["actual_cost_usd"], 0.01234567)

    def test_usage_totals_are_accumulated_even_when_json_parsing_later_fails(self):
        ledger = {"billed_input_tokens": 100, "billed_output_tokens": 200}
        billing = {"billed_input_tokens": 195304, "billed_output_tokens": 15268}
        accumulate_usage_totals(ledger, billing)
        self.assertEqual(ledger["billed_input_tokens"], 195404)
        self.assertEqual(ledger["billed_output_tokens"], 15468)

    def test_reservation_covers_observed_url_context_input_and_high_reasoning_output(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        ledger = {"calls": 3, "spent_usd": 0.62260725, "reserved_usd": 0.0}
        now = dt.datetime(2026, 11, 24, tzinfo=dt.timezone.utc)
        with patch("fact_check_analysis.read_json", return_value={
            "month": "2026-11", "spent_usd": 0.077601
        }):
            reserve = reserve_budget(config, ledger, now)
        self.assertEqual(reserve, 0.48)
        self.assertGreater(reserve, 0.34762425)
        self.assertLess(ledger["spent_usd"] + reserve, config["review_monthly_budget_usd"])
        self.assertLess(
            0.077601 + ledger["spent_usd"] + reserve,
            config["monthly_total_budget_usd"],
        )


class RetrievalMetadataTests(unittest.TestCase):
    def test_normalized_domain_accepts_bare_allowlist_hosts_and_full_urls(self):
        self.assertEqual(normalized_domain("nsi.bg"), "nsi.bg")
        self.assertEqual(normalized_domain("www.nsi.bg"), "nsi.bg")
        self.assertEqual(normalized_domain("https://www.bnb.bg/Statistics/"), "bnb.bg")
        self.assertEqual(normalized_domain(""), "")

    def test_redirected_candidate_urls_are_valid_when_every_source_retrieved(self):
        candidate = "https://www.nsi.bg/press-release/business-tendencies-9194"
        redirected = "https://www.nsi.bg/press-release/business-tendencies-october-2026-9194"
        self.assertTrue(evidence_urls_are_retrieved([candidate], [candidate], [redirected], [], 1))
        self.assertTrue(evidence_urls_are_retrieved([redirected], [candidate], [redirected], [], 1))

    def test_evidence_from_unprovided_source_is_rejected(self):
        candidate = "https://www.nsi.bg/statistics/table"
        other = "https://example.org/unprovided-source"
        self.assertFalse(evidence_urls_are_retrieved([other], [candidate], [candidate], [], 1))

    def test_partial_retrieval_coverage_is_rejected(self):
        first = "https://www.nsi.bg/statistics/table"
        second = "https://www.bnb.bg/statistics"
        self.assertFalse(evidence_urls_are_retrieved([first], [first, second], [first], [], 1))

    def test_retrieval_failures_are_never_treated_as_complete(self):
        first = "https://www.nsi.bg/statistics/table"
        second = "https://www.bnb.bg/statistics"
        failure = [{"url": second, "status": "URL_RETRIEVAL_STATUS_FAILED"}]
        self.assertFalse(evidence_urls_are_retrieved([first], [first, second], [first], failure, 1))

    def test_extract_retrieval_metadata_preserves_successful_attempt_count(self):
        payload = {"candidates": [{
            "urlContextMetadata": {"urlMetadata": [
                {"retrievedUrl": "https://www.nsi.bg/redirected", "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"},
                {"retrievedUrl": "https://www.bnb.bg/statistics", "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_SUCCESS"},
                {"retrievedUrl": "https://example.org/unavailable", "urlRetrievalStatus": "URL_RETRIEVAL_STATUS_FAILED"},
            ]}
        }]}
        urls, failures, successful_count = extract_retrieval_metadata(payload)
        self.assertEqual(successful_count, 2)
        self.assertEqual(len(urls), 2)
        self.assertEqual(len(failures), 1)


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
    candidates = set(report.get("candidate_source_urls", []))
    assert report.get("all_candidate_sources_retrieved") is True
    assert report.get("successful_source_retrieval_count") == len(candidates)
    claims = report.get("claims_checked", [])
    assert len(claims) >= 8
    for claim in claims:
        assert claim.get("verdict") == "verified"
        evidence = set(claim.get("evidence_urls", []))
        assert evidence and evidence.issubset(candidates | retrieved), "Твърдението няма доказателство от извлечен първичен URL."

    numeric_items = report.get("numeric_audit_items", [])
    assert len(numeric_items) == report.get("numeric_blocks_found")
    for item in numeric_items:
        assert item.get("verdict") == "verified"
        assert item.get("statement"), "Липсва точният числов блок, върнат от проверяващия."
        evidence = set(item.get("evidence_urls", []))
        assert evidence and evidence.issubset(candidates | retrieved)


def validate_static() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    workflow = WORKFLOW.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    disclosure = DISCLOSURE.read_text(encoding="utf-8")

    assert config["review_provider"] == "Google"
    assert config["review_model"] == "gemini-3.8-flash"
    assert config["review_reasoning_effort"] == "high"
    assert config["minimum_words"] == 900 and config["maximum_words"] == 1400
    assert config["monthly_total_budget_usd"] == 5.5
    assert config["max_factcheck_calls_per_month"] == 10
    assert config["minimum_retrieved_sources"] >= 4
    assert config["minimum_official_retrieved_domains"] >= 2
    assert config["maximum_source_urls_per_call"] <= 20
    assert config["maximum_review_input_tokens"] == 400000
    assert config["maximum_review_output_tokens"] == 48000
    assert len(config["official_source_domains"]) >= 10

    assert "automation/fix-chart-numeric-" in (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
    assert "fix/debt-counter-" in (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
    audit_workflow = (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
    assert "checks: write" in audit_workflow
    assert 'check-runs' in audit_workflow
    assert "name=editorial-approval" in audit_workflow
    assert "fix/news-ui-enforces-publisher-diversity-" in (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
    assert "fix/news-more-divider-" in (ROOT / ".github" / "workflows" / "audit-analysis-evidence.yml").read_text(encoding="utf-8")
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
    assert "calculate_billable_usage" in verifier
    assert "billed_output_tokens = candidate_output_tokens + thinking_output_tokens" in verifier
    assert "thinkingConfig" in verifier and "thinkingLevel" in verifier
    assert '"google_search"' not in verifier and '"googleSearch"' not in verifier
    assert "ANALYSES_PUBLISH_ENABLED" in verifier
    assert "official_source_domains" in verifier and "is_official_domain" in verifier
    assert "evidence_urls_are_retrieved" in verifier
    assert "successful_retrieval_count" in verifier
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
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.report:
        validate_report(Path(args.report))
    return 0




class VerifierPromptProvenanceTests(unittest.TestCase):
    def test_prompt_does_not_assume_gpt6_luna_authoring(self):
        prompt = build_prompt(
            {"title": "Тестов анализ", "lane": "bulgaria"},
            "Кратък примерен текст за независима проверка.",
            ["https://example.com/primary-source"],
            [{"item_id": "N01", "statement": "2.5% ръст през третото тримесечие"}],
            [],
        )
        self.assertIn("Авторският текст е подготвен с помощта на генеративен модел.", prompt)
        self.assertNotIn("GPT-6 Luna", prompt)




class ManualVerifierBudgetProfileTests(unittest.TestCase):
    def test_single_attempt_profile_reserve_is_exactly_03525_usd(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        workflow = MANUAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"maximum_review_input_tokens"] = 350000', workflow)
        self.assertIn('"maximum_review_output_tokens"] = 24000', workflow)
        self.assertIn('"review_reasoning_effort"] = "medium"', workflow)
        reserve = (
            350000 * float(config["review_input_usd_per_million_until_2026_12_31"])
            + 24000 * float(config["review_output_usd_per_million_until_2026_12_31"])
        ) / 1_000_000
        self.assertAlmostEqual(reserve, 0.3525, places=8)
        self.assertLessEqual(reserve, 0.3525)


if __name__ == "__main__":
    raise SystemExit(main())
