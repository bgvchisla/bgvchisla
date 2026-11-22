#!/usr/bin/env python3
"""Static security checks for the automated data writers and deployment hand-off."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_TOKEN_ACTION = "actions/create-github-app-token@f418cff399f7aef4c2f0ad47e25ca7a6abbdd6fc"
TOKEN_FALLBACK = "token: ${{ steps.automation_token.outputs.token || github.token }}"
APP_CLIENT_VARIABLE = "vars.BGVCHISLA_AUTOMATION_APP_CLIENT_ID"
APP_PRIVATE_KEY = "secrets.BGVCHISLA_AUTOMATION_APP_PRIVATE_KEY"

WRITERS = {
    ".github/workflows/check-official-sources.yml": "source_status.json",
    ".github/workflows/daily-update.yml": "economy.json",
    ".github/workflows/update-bnb-monetary.yml": "official_bnb.json",
    ".github/workflows/update-business-climate.yml": "official_business_climate.json",
    ".github/workflows/update-economy.yml": "economy.json",
    ".github/workflows/update-news.yml": "news.json",
    ".github/workflows/update-nsi-fiscal.yml": "official_fiscal.json",
    ".github/workflows/update-nssi-pensions.yml": "official_nssi.json",
}


class AutomatedWriterSecurityTests(unittest.TestCase):
    def test_every_data_writer_uses_the_dedicated_app_identity(self):
        for workflow, output_file in WRITERS.items():
            with self.subTest(workflow=workflow):
                source = (ROOT / workflow).read_text(encoding="utf-8")
                self.assertIn(APP_TOKEN_ACTION, source)
                self.assertIn(APP_CLIENT_VARIABLE, source)
                self.assertIn(APP_PRIVATE_KEY, source)
                self.assertIn(TOKEN_FALLBACK, source)
                self.assertIn("permission-contents: write", source)
                self.assertIn("APP_SLUG=", source)
                self.assertIn("actions: write", source)
                self.assertEqual(
                    source.count('git config user.name "github-actions[bot]"'),
                    1,
                    "The legacy identity may appear only in the explicit no-App fallback.",
                )
                self.assertEqual(
                    source.count('git config user.email "41898282+github-actions[bot]@users.noreply.github.com"'),
                    1,
                    "The legacy email may appear only in the explicit no-App fallback.",
                )
                self.assertIn(
                    "GH_TOKEN: ${{ steps.automation_token.outputs.token || github.token }}",
                    source,
                    "GitHub CLI must receive the same scoped token used for the checkout.",
                )

    def test_data_writers_stage_only_their_designated_output(self):
        for workflow, output_file in WRITERS.items():
            with self.subTest(workflow=workflow):
                source = (ROOT / workflow).read_text(encoding="utf-8")
                stage_lines = [
                    line.strip()
                    for line in source.splitlines()
                    if line.strip().startswith("git add ")
                ]
                self.assertEqual(
                    stage_lines,
                    [f"git add{' -f' if output_file.startswith('official_') and output_file in {'official_bnb.json', 'official_business_climate.json', 'official_nssi.json'} else ''} {output_file}"],
                    "A data writer must stage only its designated generated JSON file.",
                )

    def test_data_writers_push_without_force_and_dispatch_production(self):
        for workflow in WRITERS:
            with self.subTest(workflow=workflow):
                source = (ROOT / workflow).read_text(encoding="utf-8")
                self.assertIn("git push origin HEAD:main", source)
                self.assertNotIn("git push --force", source)
                self.assertNotIn("git push -f", source)
                self.assertIn("if: steps.save.outputs.changed == 'true'", source)
                self.assertIn("gh workflow run deploy-production.yml", source)

    def test_writers_rebase_or_safely_retry_before_push(self):
        for workflow in WRITERS:
            with self.subTest(workflow=workflow):
                source = (ROOT / workflow).read_text(encoding="utf-8")
                self.assertTrue(
                    "git pull --rebase origin main" in source or "git rebase origin/main" in source,
                    "The workflow must rebase on the latest main before retrying a non-fast-forward push.",
                )

    def test_production_deployment_is_explicit_and_does_not_duplicate_data_pushes(self):
        source = (ROOT / ".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("workflow_run:", source)
        push_section = source.split("  push:\n", 1)[1].split("\npermissions:", 1)[0]
        for output_file in set(WRITERS.values()):
            self.assertNotIn(f'"{output_file}"', push_section)
        self.assertIn("pages deploy public --project-name=bgvchisla --branch=main", source)

    def test_editorial_merge_dispatches_production_after_automated_approval(self):
        source = (ROOT / ".github/workflows/generate-analyses.yml").read_text(encoding="utf-8")
        self.assertIn('select(.context == "editorial-approval")', source)
        self.assertIn("gh api --method PUT", source)
        self.assertIn("gh workflow run deploy-production.yml", source)
        self.assertLess(source.index("gh api --method PUT"), source.index("gh workflow run deploy-production.yml"))
        self.assertNotIn("/approve", source)
        self.assertFalse((ROOT / ".github/workflows/approve-analysis.yml").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
