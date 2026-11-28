#!/usr/bin/env python3
"""Regression tests for the single, bounded underlength retry."""
from __future__ import annotations

import gzip
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analysis_retry import (  # noqa: E402
    build_retry_prompt,
    build_source_coverage_retry_prompt,
    canonical_used_source_ids,
    insufficient_source_count,
    maximum_retry_reserve,
    maximum_single_call_reserve,
    underlength_word_count,
)
from patch_analysis_evidence import patch_source  # noqa: E402


class AnalysisRetryTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "minimum_words": 900,
            "maximum_words": 1400,
            "minimum_sources": 4,
            "maximum_prompt_characters": 65000,
            "max_output_tokens": 5500,
            "input_usd_per_million": 0.1,
            "output_usd_per_million": 0.5,
        }

    def test_only_exact_underlength_error_is_retryable(self):
        self.assertEqual(underlength_word_count("Word count out of range: 871", 900), 871)
        self.assertEqual(underlength_word_count("Word count out of range: 899", 900), 899)
        self.assertIsNone(underlength_word_count("Word count out of range: 900", 900))
        self.assertIsNone(underlength_word_count("Word count out of range: 1401", 900))
        self.assertIsNone(underlength_word_count("Paragraph evidence validation failed", 900))
        self.assertIsNone(underlength_word_count("OpenAI API HTTP 429", 900))

    def test_only_exact_insufficient_source_count_error_is_retryable(self):
        error = "Source validation failed: only 3 distinct valid sources are cited; minimum is 4."
        self.assertEqual(insufficient_source_count(error, 4), 3)
        self.assertIsNone(insufficient_source_count("Source validation failed", 4))
        self.assertIsNone(insufficient_source_count("Paragraph evidence validation failed", 4))
        self.assertIsNone(insufficient_source_count(
            "Source validation failed: only 4 distinct valid sources are cited; minimum is 4.", 4
        ))
        self.assertIsNone(insufficient_source_count(error, 5))

    def test_source_coverage_retry_uses_same_evidence_and_draft(self):
        evidence = {"sources": [{"source_id": "D01"}, {"source_id": "N01"}]}
        draft = {"title": "Тест", "sections": [{"paragraphs": [{"text": "Чернова"}]}]}
        prompt = build_source_coverage_retry_prompt(evidence, draft, 3, self.config)
        payload = json.loads(prompt)
        self.assertEqual(payload["evidence"], evidence)
        self.assertEqual(payload["previous_draft"], draft)
        self.assertIn("поне 4 различни source_id", payload["assignment"])
        self.assertIn("не го използвай", payload["assignment"])
        self.assertIn("1050-1150 думи", payload["assignment"])
        self.assertIn("не измисляй факти", payload["assignment"])
        self.assertLessEqual(len(prompt), self.config["maximum_prompt_characters"])

    def test_source_coverage_retry_is_refused_when_minimum_is_met(self):
        with self.assertRaises(ValueError):
            build_source_coverage_retry_prompt({}, {}, 4, self.config)

    def test_source_coverage_retry_prompt_size_guard_blocks_second_call(self):
        config = dict(self.config, maximum_prompt_characters=80)
        with self.assertRaisesRegex(RuntimeError, "source-coverage retry was not made"):
            build_source_coverage_retry_prompt({"sources": ["x" * 200]}, {}, 3, config)

    def test_retry_prompt_keeps_original_evidence_and_draft(self):
        evidence = {"sources": [{"source_id": "N01", "url": "https://example.com"}]}
        draft = {"title": "Тест", "sections": [{"paragraphs": [{"text": "Чернова"}]}]}
        prompt = build_retry_prompt(evidence, draft, 871, self.config)
        payload = json.loads(prompt)
        self.assertEqual(payload["evidence"], evidence)
        self.assertEqual(payload["previous_draft"], draft)
        self.assertIn("1050-1150 думи", payload["assignment"])
        self.assertIn("900-1400 думи", payload["assignment"])
        self.assertIn("Не измисляй липсващи стойности", payload["assignment"])
        self.assertLessEqual(len(prompt), self.config["maximum_prompt_characters"])

    def test_retry_is_refused_for_a_draft_already_at_minimum(self):
        with self.assertRaises(ValueError):
            build_retry_prompt({}, {}, 900, self.config)

    def test_retry_prompt_size_guard_prevents_second_call_payload(self):
        config = dict(self.config, maximum_prompt_characters=80)
        with self.assertRaisesRegex(RuntimeError, "Retry prompt size guard"):
            build_retry_prompt({"evidence": "x" * 200}, {"draft": "y"}, 871, config)

    def test_budget_reserves_one_or_two_worst_case_calls(self):
        one_call = maximum_single_call_reserve(self.config)
        two_calls = maximum_retry_reserve(self.config)
        expected_one_call = (
            self.config["maximum_prompt_characters"] * self.config["input_usd_per_million"]
            + self.config["max_output_tokens"] * self.config["output_usd_per_million"]
        ) / 1_000_000
        self.assertAlmostEqual(one_call, expected_one_call, places=6)
        self.assertAlmostEqual(two_calls, one_call * 2, places=6)
        self.assertGreater(two_calls, one_call)

    def test_source_ids_are_derived_from_actual_valid_citations(self):
        index = {f"N{i:02d}": {"source_id": f"N{i:02d}"} for i in range(1, 6)}
        cited = {"N01", "N03", "N04", "N05"}
        self.assertEqual(canonical_used_source_ids(cited, index, 4), ["N01", "N03", "N04", "N05"])

    def test_source_ids_require_four_distinct_citations(self):
        index = {f"N{i:02d}": {} for i in range(1, 6)}
        with self.assertRaisesRegex(RuntimeError, "only 3 distinct valid sources"):
            canonical_used_source_ids({"N01", "N02", "N03"}, index, 4)

    def test_source_ids_reject_any_unknown_citation(self):
        index = {"N01": {}, "N02": {}, "N03": {}, "N04": {}}
        with self.assertRaisesRegex(RuntimeError, "unknown cited source_id"):
            canonical_used_source_ids({"N01", "N02", "N03", "N04", "N99"}, index, 4)

    def test_runtime_patcher_adds_both_bounded_retries_and_is_idempotent(self):
        compressed = ROOT / "scripts" / "generate_analysis.py.gz"
        original = gzip.decompress(compressed.read_bytes()).decode("utf-8")
        patched = patch_source(original)
        compile(patched, "generate_analysis.py", "exec")
        self.assertEqual(patched.count("retry_prompt=build_retry_prompt(pack,a,first_words,cfg)"), 1)
        self.assertEqual(patched.count("retry_a,retry_u,retry_cost=api(retry_prompt,cfg)"), 1)
        self.assertIn("retry_allowed=calls+2<=cfg['max_api_calls_per_month']", patched)
        self.assertIn("maximum_retry_reserve(cfg)", patched)
        self.assertIn("maximum_single_call_reserve(cfg)", patched)
        self.assertIn("if not retry_allowed:", patched)
        self.assertIn("BGVCHV_MINIMUM_SECTIONS_GUARD", patched)
        self.assertIn("sections трябва да съдържа минимум", patched)
        self.assertIn('prompt += "\\n\\n" + section_instruction', patched)
        self.assertIn("calls>=cfg['max_api_calls_per_month']", patched)
        self.assertIn("canonical_used_source_ids(cited,src,cfg['minimum_sources'])", patched)
        self.assertIn("used_source_ids трябва да съдържа всички различни source_id", patched)
        self.assertIn("build_source_coverage_retry_prompt(pack,a,source_count,cfg)", patched)
        self.assertIn("target=R/'analizi'/slug/'index.html'", patched)
        self.assertIn("publish_article(R,a,args.lane,now,label,page,slug)", patched)
        self.assertNotIn("key=lambda x:x['date']", patched)
        self.assertIn("Използвай съдържателно поне 4 различни source_id", patched)
        self.assertIn("publish_article(R,a,args.lane,now,label,page,slug)", patched)
        self.assertNotIn("key=lambda x:x['date']", patched)
        self.assertEqual(patch_source(patched), patched)


if __name__ == "__main__":
    unittest.main(verbosity=2)
