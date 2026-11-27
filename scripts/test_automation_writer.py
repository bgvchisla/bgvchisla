#!/usr/bin/env python3
"""Static security checks for PR-first automated data writers."""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_TOKEN_ACTION = "actions/create-github-app-token@f418cff399f7aef4c2f0ad47e25ca7a6abbdd6fc"
TOKEN_FALLBACK = "token: ${{ steps.automation_token.outputs.token || github.token }}"
APP_CLIENT_VARIABLE = "vars.BGVCHISLA_AUTOMATION_APP_CLIENT_ID"
APP_PRIVATE_KEY = "secrets.BGVCHISLA_AUTOMATION_APP_PRIVATE_KEY"
WRITERS = {
 ".github/workflows/check-official-sources.yml":"source_status.json",
 ".github/workflows/daily-update.yml":"economy.json",
 ".github/workflows/update-bnb-monetary.yml":"official_bnb.json",
 ".github/workflows/update-business-climate.yml":"official_business_climate.json",
 ".github/workflows/update-economy.yml":"economy.json",
 ".github/workflows/update-inflation.yml":"inflation.json",
 ".github/workflows/update-labour-market.yml":"labour-market.json",
 ".github/workflows/update-news.yml":"news.json",
 ".github/workflows/update-nsi-fiscal.yml":"official_fiscal.json",
 ".github/workflows/update-nssi-pensions.yml":"official_nssi.json",
}
class AutomatedWriterSecurityTests(unittest.TestCase):
 def test_all_ten_writers_use_scoped_app_token_with_pr_permission(self):
  self.assertEqual(len(WRITERS),10)
  for workflow in WRITERS:
   with self.subTest(workflow=workflow):
    s=(ROOT/workflow).read_text(encoding="utf-8")
    for required in (APP_TOKEN_ACTION,APP_CLIENT_VARIABLE,APP_PRIVATE_KEY,TOKEN_FALLBACK,"permission-contents: write","permission-pull-requests: write","pull-requests: write","scripts/create_data_update_pr.sh"):
     self.assertIn(required,s)
    self.assertIn("GH_TOKEN: ${{ steps.automation_token.outputs.token || github.token }}",s)
 def test_writers_never_push_main_or_dispatch_deployment(self):
  for workflow in WRITERS:
   with self.subTest(workflow=workflow):
    s=(ROOT/workflow).read_text(encoding="utf-8")
    for forbidden in ("git push","git pull --rebase","git rebase origin/main","gh workflow run deploy-production.yml"):
     self.assertNotIn(forbidden,s)
 def test_helper_is_allowlisted_and_creates_pr(self):
  s=(ROOT/"scripts/create_data_update_pr.sh").read_text(encoding="utf-8")
  for required in ('case "$OUTPUT_FILE" in','git add -- "$OUTPUT_FILE"','git add -f -- "$OUTPUT_FILE"','git switch -c "$BRANCH"','git push --set-upstream origin "$BRANCH"','gh pr create','--base main','automation/data-update-'):
   self.assertIn(required,s)
  self.assertNotIn("HEAD:main",s)
  self.assertNotIn("git add .",s)
 def test_each_writer_uses_its_designated_output(self):
  h=(ROOT/"scripts/create_data_update_pr.sh").read_text(encoding="utf-8")
  for workflow,output in WRITERS.items():
   with self.subTest(workflow=workflow):
    s=(ROOT/workflow).read_text(encoding="utf-8")
    self.assertIn(f"scripts/create_data_update_pr.sh {output}",s)
    self.assertIn(output,h)
 def test_production_deploys_from_main_after_merge(self):
  s=(ROOT/".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
  self.assertIn("branches: [main]",s)
  for dataset in ("source_status.json","economy.json","official_bnb.json","official_business_climate.json","inflation.json","labour-market.json","news.json","official_fiscal.json","official_nssi.json"):
   self.assertIn(f'"{dataset}"',s)
  self.assertIn("pages deploy public --project-name=bgvchisla --branch=main",s)
 def test_analysis_publication_keeps_guarded_merge_and_deploy(self):
  s=(ROOT/".github/workflows/generate-analyses.yml").read_text(encoding="utf-8")
  self.assertIn('select(.context == "editorial-approval")',s)
  self.assertIn("gh api --method PUT",s)
  self.assertIn("gh workflow run deploy-production.yml",s)
  self.assertLess(s.index("gh api --method PUT"),s.index("gh workflow run deploy-production.yml"))
  self.assertNotIn("/approve",s)
  self.assertFalse((ROOT/".github/workflows/approve-analysis.yml").exists())
if __name__=="__main__":
 unittest.main(verbosity=2)
