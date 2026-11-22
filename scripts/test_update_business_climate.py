#!/usr/bin/env python3
"""Regression tests for safe NSI business-climate update behavior."""
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_business_climate


class BusinessClimateAvailabilityTests(unittest.TestCase):
    def make_http_error(self, code):
        return urllib.error.HTTPError(
            update_business_climate.INDEX,
            code,
            "upstream response",
            hdrs=None,
            fp=None,
        )

    def test_403_keeps_last_validated_dataset_unchanged(self):
        original = (
            '{"reference_date":"2026-10","values":{"total":{"value":13.2}},'
            '"updated_at":"2026-11-18T22:57:58Z"}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "official_business_climate.json"
            target.write_text(original, encoding="utf-8")
            with patch.object(update_business_climate, "OUT", target), patch.object(
                update_business_climate, "get", side_effect=self.make_http_error(403)
            ):
                update_business_climate.main()
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_403_without_previous_validated_dataset_remains_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing.json"
            with patch.object(update_business_climate, "OUT", target), patch.object(
                update_business_climate, "get", side_effect=self.make_http_error(403)
            ):
                with self.assertRaises(urllib.error.HTTPError):
                    update_business_climate.main()

    def test_non_403_http_errors_are_not_silenced(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "official_business_climate.json"
            target.write_text('{"reference_date":"2026-10"}\n', encoding="utf-8")
            with patch.object(update_business_climate, "OUT", target), patch.object(
                update_business_climate, "get", side_effect=self.make_http_error(500)
            ):
                with self.assertRaises(urllib.error.HTTPError):
                    update_business_climate.main()


if __name__ == "__main__":
    unittest.main(verbosity=2)
