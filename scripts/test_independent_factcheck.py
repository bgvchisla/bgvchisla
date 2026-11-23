#!/usr/bin/env python3
"""Static and report-integrity tests for the independent fact-check gate."""
from __future__ import annotations
import argparse, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "analysis" / "config.json"
WORKFLOW = ROOT / ".github" / "workflows" / "generate-analyses.yml"
VERIFIER = ROOT / "scripts" / "fact_check_analysis.py"
DISCLOSURE = ROOT / "scripts" / "apply_ai_disclosure.py"

def validate_report(path):
    r = json.loads(path.read_text(encoding="utf-8"))
    assert r.get("overall_verdict") == "PASS", "Независимият fact-check не е PASS."
    assert r.get("review_provider") == "Google" and r.get("review_model") == "gemini-3.8-flash"
    assert r.get("review_method") == "Gemini API with Google Search grounding"
    assert int(r.get("verified_claims", 0)) >= 8 and int(r.get("grounded_source_count", 0)) >= 4
    assert int(r.get("numeric_claims_found", 0)) > 0
    assert r.get("numeric_claims_verified") == r.get("numeric_claims_found")
    assert not r.get("blocking_reasons")
    grounded, claims = set(r.get("grounded_sources", [])), r.get("claims_checked", [])
    assert len(claims) >= 8
    for claim in claims:
        assert claim.get("verdict") == "verified"
        assert any(url in grounded for url in claim.get("evidence_urls", [])), "Липсва независим grounding URL."

def validate_static():
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    w, v, d = WORKFLOW.read_text(encoding="utf-8"), VERIFIER.read_text(encoding="utf-8"), DISCLOSURE.read_text(encoding="utf-8")
    assert c["review_provider"] == "Google" and c["review_model"] == "gemini-3.8-flash"
    assert c["minimum_words"] == 900 and c["maximum_words"] == 1400
    assert c["monthly_total_budget_usd"] == 5.5 and c["max_factcheck_calls_per_month"] == 12
    assert "ANALYSES_PUBLISH_ENABLED" in w and "GEMINI_API_KEY" in w
    assert "steps.factcheck.outputs.verdict == 'PASS'" in w
    assert "fact_check_analysis.py" in w and "apply_ai_disclosure.py" in w
    assert "gemini-3.8-flash" in v and "googleSearch" in v and "groundingMetadata" in v
    assert "ANALYSES_PUBLISH_ENABLED" in v and "ai-disclosure" in d
    assert "Не е преминал човешка редакционна проверка" in d
    assert "ANALYSES_AUTODRAFT_ENABLED" not in w and "/approve" not in w
    print("Статичните проверки за независима фактологична верификация са успешни.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--static", action="store_true")
    p.add_argument("--report")
    a = p.parse_args()
    if a.static: validate_static()
    if a.report: validate_report(Path(a.report))
    return 0
if __name__ == "__main__": raise SystemExit(main())
