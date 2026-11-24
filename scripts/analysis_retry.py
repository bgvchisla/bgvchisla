#!/usr/bin/env python3
"""Single, budget-bounded editorial retry and canonical source-ID validation."""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping


def underlength_word_count(error: BaseException | str, minimum_words: int) -> int | None:
    """Return a word count only for the precise under-minimum validation error."""
    match = re.fullmatch(r"Word count out of range: (\d+)", str(error).strip())
    if not match:
        return None
    words = int(match.group(1))
    return words if words < int(minimum_words) else None


def insufficient_source_count(error: BaseException | str, minimum_sources: int) -> int | None:
    """Return the observed count only for the precise insufficient-citations error."""
    match = re.fullmatch(
        r"Source validation failed: only (\d+) distinct valid sources are cited; minimum is (\d+)\.",
        str(error).strip(),
    )
    if not match:
        return None
    observed, configured_minimum = map(int, match.groups())
    if configured_minimum != int(minimum_sources) or observed >= int(minimum_sources):
        return None
    return observed


def canonical_used_source_ids(
    cited_source_ids: Iterable[str],
    source_index: Mapping[str, Any],
    minimum_sources: int,
) -> list[str]:
    """Derive the canonical source list from citations actually present in the draft."""
    cited = {str(value) for value in cited_source_ids}
    invalid = sorted(value for value in cited if value not in source_index)
    if invalid:
        raise RuntimeError(
            "Source validation failed: unknown cited source_id(s): " + ", ".join(invalid)
        )
    if len(cited) < int(minimum_sources):
        raise RuntimeError(
            f"Source validation failed: only {len(cited)} distinct valid sources are cited; "
            f"minimum is {int(minimum_sources)}."
        )
    return sorted(cited)


def maximum_retry_reserve(config: dict[str, Any]) -> float:
    """Reserve the configured worst-case prompt/output allowance for two calls."""
    one_call = (
        int(config["maximum_prompt_characters"]) * float(config["input_usd_per_million"])
        + int(config["max_output_tokens"]) * float(config["output_usd_per_million"])
    ) / 1_000_000
    return round(one_call * 2, 6)


def build_retry_prompt(
    evidence: dict[str, Any],
    previous_draft: dict[str, Any],
    first_word_count: int,
    config: dict[str, Any],
) -> str:
    """Build one evidence-locked rewrite prompt after a confirmed word-count underflow."""
    minimum = int(config["minimum_words"])
    maximum = int(config["maximum_words"])
    if first_word_count >= minimum:
        raise ValueError("A retry is permitted only for a draft below the minimum word count.")

    assignment = (
        "Напиши цялостна, завършена редакция на предишния икономически анализ. "
        f"Предишната чернова съдържаше {first_word_count} думи в текста на секционните параграфи "
        f"и не покрива минимума от {minimum} думи. "
        "Целевата дължина на текста в sections[].paragraphs[].text е 1050-1150 думи. "
        f"Абсолютните граници остават {minimum}-{maximum} думи. "
        "Броят се думите само в текста на параграфите в sections[].paragraphs[].text, "
        "не в заглавието, резюмето, ключовите точки или методологичната бележка. "
        "Не добавяй празни фрази и не повтаряй една и съща теза. "
        "Разшири анализа с проверими обяснения на икономическите механизми, "
        "връзките между представените данни, последиците за домакинствата, бизнеса и публичните финанси, "
        "релевантните рискове, алтернативните сценарии и ограниченията на наличните доказателства. "
        "Използвай само фактите, числата, датите и URL адресите от предоставения evidence пакет. "
        "Не измисляй липсващи стойности и не представяй международен контекст като доказан ефект върху България. "
        "Всеки параграф трябва да съдържа поне 24 думи и да цитира точните source_ids, които го подкрепят. "
        "Полето used_source_ids трябва да съдържа всички различни source_id, използвани в параграфите и ключовите изводи. "
        "Запази задължителната JSON схема, валидните source_ids, методологичната бележка и ключовите изводи. "
        "Не добавяй нови източници и не променяй доказателствената основа. "
        "Върни пълния анализ, а не само допълнителни абзаци."
    )
    prompt = json.dumps(
        {"assignment": assignment, "evidence": evidence, "previous_draft": previous_draft},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(prompt) > int(config["maximum_prompt_characters"]):
        raise RuntimeError("Retry prompt size guard reached; second API call was not made.")
    return prompt


def build_source_coverage_retry_prompt(
    evidence: dict[str, Any],
    previous_draft: dict[str, Any],
    observed_source_count: int,
    config: dict[str, Any],
) -> str:
    """Build one full rewrite prompt for a draft that cites too few distinct valid sources."""
    minimum_sources = int(config["minimum_sources"])
    minimum_words = int(config["minimum_words"])
    maximum_words = int(config["maximum_words"])
    if observed_source_count >= minimum_sources:
        raise ValueError("A source-coverage retry is permitted only below the source minimum.")

    assignment = (
        "Напиши цялостна, завършена редакция на предишния икономически анализ. "
        f"Предишната чернова използва само {observed_source_count} различни валидни source_id; "
        f"минимумът е {minimum_sources}. "
        f"Използвай съдържателно поне {minimum_sources} различни source_id от предоставения evidence пакет. "
        "Това не е формално изискване за библиография: всеки използван източник трябва да подкрепя "
        "конкретен факт, число, сравнение или извод в съответния параграф или ключова точка. "
        "Провери наличните официални набори от данни и новинарски материали и включи четвърти "
        "и следващи източници само когато пакетът действително съдържа релевантни доказателства. "
        "Не цитирай източник само за достигане на бройката, не добавяй неподкрепени твърдения "
        "и не измисляй факти, стойности, периоди, методология или URL адреси. "
        "Ако даден източник не подкрепя конкретна теза, не го използвай. "
        "Запази разграничението между български данни и международен контекст. "
        "Всеки параграф трябва да съдържа поне 24 думи и да цитира точните source_ids, които го подкрепят. "
        f"Дължината на текста в секционните параграфи трябва да бъде между {minimum_words} и {maximum_words} думи; "
        "цели се в 1050-1150 думи без повторения и празни фрази. "
        "Полето used_source_ids трябва да съдържа точно всички различни source_id, използвани "
        "в параграфите и ключовите изводи. "
        "Запази задължителната JSON схема, поне четири смислени секции, ключовите изводи, "
        "заключението и методологичната бележка. "
        "Върни пълния анализ, а не само допълнителни абзаци."
    )
    prompt = json.dumps(
        {
            "assignment": assignment,
            "evidence": evidence,
            "previous_draft": previous_draft,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(prompt) > int(config["maximum_prompt_characters"]):
        raise RuntimeError("Retry prompt size guard reached; source-coverage retry was not made.")
    return prompt
