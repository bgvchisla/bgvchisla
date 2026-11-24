#!/usr/bin/env python3
"""Install strict evidence selection and a single bounded underlength retry."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_analysis.py"


def patch_source(source: str) -> str:
    patched = source
    import_line = "from analysis_evidence import get_evidence as _strict_get_evidence"

    if import_line not in patched:
        start_marker = "def get_evidence(lane):"
        end_marker = "def api(prompt,cfg):"
        if patched.count(start_marker) != 1:
            raise RuntimeError("Очакваше се точно една функция get_evidence(lane).")
        start = patched.index(start_marker)
        end = patched.find(end_marker, start)
        if end < 0:
            raise RuntimeError("Не е намерена границата преди api(prompt,cfg).")
        replacement = '''from analysis_evidence import get_evidence as _strict_get_evidence

def get_evidence(lane):
    pack = _strict_get_evidence(lane)
    for item in pack["sources"]:
        if str(item.get("source_id", "")).startswith("N"):
            print(
                "ПОДБРАН МАТЕРИАЛ |",
                item.get("editorial_role", ""),
                "|",
                item.get("publisher", ""),
                "|",
                item.get("published", ""),
                "|",
                item.get("title", ""),
                "|",
                item.get("url", ""),
            )
    return pack


'''
        patched = patched[:start] + replacement + patched[end:]

    # Международният контекст не се представя като доказан български ефект.
    context_phrase = "Материалите, маркирани като „Международен контекст за България“"
    if context_phrase not in patched:
        context_guard = (
            "Не добавяй неподкрепени числа. "
            "Материалите, маркирани като „Международен контекст за България“, "
            "служат само за външен контекст. Не твърди конкретен ефект върху България, "
            "освен когато той е изрично подкрепен от предоставени данни или източник."
        )
        needle = "Не добавяй неподкрепени числа."
        if patched.count(needle) != 1:
            raise RuntimeError("Не е намерено еднозначно място за контрола на международния контекст.")
        patched = patched.replace(needle, context_guard, 1)

    # Само една повторна заявка е разрешена и само при точна грешка за под 900 думи.
    retry_marker = "retry_prompt=build_retry_prompt(pack,a,first_words,cfg)"
    if retry_marker not in patched:
        needle = (
            "a,u,cost=api(prompt,cfg);record_usage(u,cost,cfg);"
            "a=validate(a,pack,cfg);now=dt.datetime.now(TZ);label=now.strftime('%d.%m.%Y')"
        )
        if patched.count(needle) != 1:
            raise RuntimeError("Не е намерено еднозначно място за ограничения редакционен повторен опит.")
        replacement = """a,u,cost=api(prompt,cfg);record_usage(u,cost,cfg)
 try:
  a=validate(a,pack,cfg)
 except RuntimeError as exc:
  from analysis_retry import build_retry_prompt, underlength_word_count
  first_words=underlength_word_count(exc,cfg['minimum_words'])
  if first_words is None:raise
  print(f'ЕДИН ПОВТОРЕН ОПИТ: първата чернова е {first_words} думи; минимумът е {cfg["minimum_words"]}.')
  retry_prompt=build_retry_prompt(pack,a,first_words,cfg)
  retry_a,retry_u,retry_cost=api(retry_prompt,cfg)
  record_usage(retry_u,retry_cost,cfg)
  cost+=retry_cost
  a=validate(retry_a,pack,cfg)
 now=dt.datetime.now(TZ);label=now.strftime('%d.%m.%Y')"""
        patched = patched.replace(needle, replacement, 1)

    # Предварително се резервира максималната стойност за първата заявка и един повторен опит.
    reserve_marker = "maximum_retry_reserve(cfg)"
    if reserve_marker not in patched:
        estimate_needle = (
            "estimate=(len(prompt)*cfg['input_usd_per_million']+"
            "cfg['max_output_tokens']*cfg['output_usd_per_million'])/1e6"
        )
        if patched.count(estimate_needle) != 1:
            raise RuntimeError("Не е намерено еднозначно място за предварителния бюджетен резерв.")
        patched = patched.replace(
            estimate_needle,
            "from analysis_retry import maximum_retry_reserve\n estimate=maximum_retry_reserve(cfg)",
            1,
        )
        calls_needle = (
            "if spent+estimate>cfg['monthly_budget_usd'] or calls>=cfg['max_api_calls_per_month']:"
        )
        if patched.count(calls_needle) != 1:
            raise RuntimeError("Не е намерена бюджетната проверка за броя заявки.")
        patched = patched.replace(
            calls_needle,
            "if spent+estimate>cfg['monthly_budget_usd'] or calls+2>cfg['max_api_calls_per_month']:",
            1,
        )

    ast.parse(patched, filename=str(GENERATOR))
    return patched


def main() -> None:
    if not GENERATOR.exists():
        raise SystemExit("Липсва разархивираният генератор на анализи.")
    source = GENERATOR.read_text(encoding="utf-8")
    patched = patch_source(source)
    GENERATOR.write_text(patched, encoding="utf-8")
    print("Включени са строгият редакционен селектор, защитата срещу неподкрепени изводи и еднократният бюджетно ограничен повторен опит.")


if __name__ == "__main__":
    main()
