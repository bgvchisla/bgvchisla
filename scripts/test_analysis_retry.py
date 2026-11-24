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
    maximum_retry_reserve,
    underlength_word_count,
)
from patch_analysis_evidence import patch_source  # noqa: E402


class AnalysisRetryTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "minimum_words": 900,
            "maximum_words": 1400,
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

    def test_budget_reserves_two_worst_case_calls(self):
        reserve = maximum_retry_reserve(self.config)
        one_call = (
            self.config["maximum_prompt_characters"] * self.config["input_usd_per_million"]
            + self.config["max_output_tokens"] * self.config["output_usd_per_million"]
        ) / 1_000_000
        self.assertAlmostEqual(reserve, one_call * 2, places=6)
        self.assertGreater(reserve, one_call)

    def test_runtime_patcher_adds_exactly_one_retry_and_is_idempotent(self):
        compressed = ROOT / "scripts" / "generate_analysis.py.gz"
        original = gzip.decompress(compressed.read_bytes()).decode("utf-8")
        patched = patch_source(original)
        compile(patched, "generate_analysis.py", "exec")
        self.assertEqual(patched.count("retry_prompt=build_retry_prompt(pack,a,first_words,cfg)"), 1)
        self.assertEqual(patched.count("retry_a,retry_u,retry_cost=api(retry_prompt,cfg)"), 1)
        self.assertIn("calls+2>cfg['max_api_calls_per_month']", patched)
        self.assertIn("maximum_retry_reserve(cfg)", patched)
        self.assertEqual(patch_source(patched), patched)


if __name__ == "__main__":
    unittest.main(verbosity=2)
