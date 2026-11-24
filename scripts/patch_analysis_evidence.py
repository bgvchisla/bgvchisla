#!/usr/bin/env python3
"""Install strict evidence selection, source-ID normalization and one bounded retry."""
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

    # Указваме на модела точния агрегат от реално цитираните източници.
    source_instruction = "Всеки абзац и всеки основен извод трябва да цитира source_ids."
    source_instruction_extra = (
        source_instruction
        + " Полето used_source_ids трябва да съдържа всички различни source_id, "
        "използвани в параграфите и ключовите изводи, без други идентификатори. "
        "Използвай съдържателно поне 4 различни source_id от evidence пакета; не добавяй несъществуващи цитати."
    )
    if source_instruction_extra not in patched:
        if patched.count(source_instruction) != 1:
            raise RuntimeError("Не е намерена еднозначна инструкция за source_ids.")
        patched = patched.replace(source_instruction, source_instruction_extra, 1)

    # used_source_ids дублира цитатите в абзаците/ключовите изводи.
    # Изчисляваме го от тях, но пазим строгата проверка за минимум 4 валидни източника.
    normalization_marker = "canonical_used_source_ids(cited,src,cfg['minimum_sources'])"
    if normalization_marker not in patched:
        initial_guard = (
            "if len(set(used))<cfg['minimum_sources'] or any(x not in src for x in used):"
            "raise RuntimeError('Source validation failed')"
        )
        if patched.count(initial_guard) != 1:
            raise RuntimeError("Не е намерена еднозначна първоначална проверка за source IDs.")
        patched = patched.replace(
            initial_guard,
            "if not isinstance(used,list):raise RuntimeError('Source validation failed: used_source_ids is not a list')",
            1,
        )
        consistency_guard = "if set(used)!=cited:raise RuntimeError('Every cited source must appear in the source list, and every listed source must be cited')"
        if patched.count(consistency_guard) != 1:
            raise RuntimeError("Не е намерена еднозначна финална проверка за съвпадение на source IDs.")
        patched = patched.replace(
            consistency_guard,
            "from analysis_retry import canonical_used_source_ids\n "
            "a['used_source_ids']=canonical_used_source_ids(cited,src,cfg['minimum_sources'])",
            1,
        )

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
  from analysis_retry import (build_retry_prompt, build_source_coverage_retry_prompt, underlength_word_count, insufficient_source_count)
  first_words=underlength_word_count(exc,cfg['minimum_words'])
  source_count=insufficient_source_count(exc,cfg['minimum_sources'])
  if first_words is not None:
   print(f'ЕДИН ПОВТОРЕН ОПИТ: първата чернова е {first_words} думи; минимумът е {cfg["minimum_words"]}.')
   retry_prompt=build_retry_prompt(pack,a,first_words,cfg)
  elif source_count is not None:
   print(f'ЕДИН ПОВТОРЕН ОПИТ: черновата цитира {source_count} различни източника; минимумът е {cfg["minimum_sources"]}.')
   retry_prompt=build_source_coverage_retry_prompt(pack,a,source_count,cfg)
  else:raise
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

    # Заменяме legacy single-file output с модерния сайт договор:
    # /analizi/{slug}/index.html, published_at registry, архивна карта и sitemap.
    target_old = "name=f'{now:%Y-%m-%d}-{slug}.html';target=R/'analizi'/name"
    target_new = "name=f'{now:%Y-%m-%d}-{slug}.html';target=R/'analizi'/slug/'index.html'"
    if target_old in patched:
        patched = patched.replace(target_old, target_new, 1)
    elif target_new not in patched:
        raise RuntimeError("Не е намерена еднозначна legacy цел за HTML страницата.")

    publish_start = " target.parent.mkdir(parents=True,exist_ok=True);target.write_text(page,encoding='utf-8');src=a['_src'];ids=a['used_source_ids']"
    if publish_start in patched:
        publish_start_index = patched.index(publish_start)
        guard_index = patched.find("if __name__=='__main__':", publish_start_index)
        if guard_index < 0:
            raise RuntimeError("Не е намерен край на legacy publishing блока.")
        publish_end = patched.rfind("\n", publish_start_index, guard_index)
        if publish_end < 0:
            raise RuntimeError("Не е намерена граница на реда преди main guard.")
        patched = (
            patched[:publish_start_index]
            + " from analysis_publishing import publish_article\n publish_article(R,a,args.lane,now,label,page,slug)"
            + patched[publish_end:]
        )
    elif "publish_article(R,a,args.lane,now,label,page,slug)" not in patched:
        raise RuntimeError("Не е намерен еднозначен legacy publishing блок.")

    ast.parse(patched, filename=str(GENERATOR))
    return patched


def main() -> None:
    if not GENERATOR.exists():
        raise SystemExit("Липсва разархивираният генератор на анализи.")
    source = GENERATOR.read_text(encoding="utf-8")
    patched = patch_source(source)
    GENERATOR.write_text(patched, encoding="utf-8")
    print("Включени са строгият редакционен селектор, контекстната защита, канонизирането на source IDs и еднократният бюджетно ограничен повторен опит.")


if __name__ == "__main__":
    main()
