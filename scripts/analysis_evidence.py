#!/usr/bin/env python3
"""Строг редакционен подбор на доказателства за автоматизираните анализи."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "news": "news.json",
    "fiscal": "official_fiscal.json",
    "economy": "economy.json",
    "bnb": "official_bnb.json",
    "nssi": "official_nssi.json",
    "business": "official_business_climate.json",
    "articles": "analizi/articles.json",
}

# За българския анализ се изисква ясна икономическа тема още в заглавието.
BG_CORE_TERMS = (
    "бюджет", "държавен дълг", "публичен дълг", "бвп", "икономик",
    "инфлац", "данък", "данъч", "осигур", "заплат", "доход", "пенси",
    "социал", "зает", "безработ", "лихв", "кредит", "депозит", "банков",
    "банка", "финанс", "инвести", "износ", "внос", "търгов", "енерг",
    "електроенерг", "горив", "производител", "бизнес", "предприят",
    "компан", "фирм", "промишлен", "строителств", "земедел", "пву",
    "възстановяване", "еврофонд", "субсид", "държавна помощ", "акциз",
    "ддс", "митниц", "валут", "резерв", "капитал", "облигац",
    "покупател", "потребител", "пазар на труда",
)

WORLD_TERMS = (
    "econom", "inflation", "interest rate", "central bank", "ecb", "fed",
    "fomc", "gdp", "trade", "tariff", "budget", "debt", "bond", "market",
    "energy", "oil", "gas", "investment", "financial", "finance", "fiscal",
    "monetary", "capital", "productivity", "employment", "tax", "lagarde",
    "banking", "bank", "liquidity", "payments", "credit", "federal", "imf",
    "oecd", "world bank", "финанс", "лихв", "иконом", "пазар", "енерг",
    "газ", "петрол", "облигац", "търгов", "инфлац", "бюджет", "дълг",
)

# Ако чуждестранната тема не съдържа изрична българска връзка, тя не влиза
# в списъка с вътрешни български материали.
FOREIGN_FOCUS_TERMS = (
    "европа", "европей", "евросъюз", "еврозон", "ецб", "фед",
    "федералн", "гърц", "гръц", "американ", "съединените щати", "саш",
    "китай", "китайск", "руси", "украйн", "израел", "иран", "нато",
    "франц", "герман", "итал", "испан", "полш", "нидерланд",
    "португал", "япон", "индий", "глобал", "световн", "международн",
    "opec", "imf", "world bank", "united states", "europe", "euro area",
    "ecb", "federal reserve", "germany", "france", "china", "greece",
)
DOMESTIC_MARKERS = (
    "българ", "у нас", "в страната", "за българ", "на българ", "бнб",
    "нси", "нои", "министерство на финансите", "софия",
    "българския бизнес", "българските фирми", "българските домакинства",
)

# Допускаме ограничен международен контекст само когато има ясен канал
# към българската икономика. Показваме го отделно от вътрешните новини.
CONTEXT_RULES = (
    ("Енергиен пазар на ЕС", 38, (
        "европейски енергиен пазар", "енергиен пазар в европа",
        "european energy market", "енергийният пазар на ес",
    )),
    ("Дългосрочен бюджет на ЕС", 32, (
        "европейския съюз", "европейският съюз", "дългосрочния бюджет",
        "eu budget", "long-term budget", "multiannual financial framework",
    )),
    ("Инфлация в еврозоната", 29, (
        "euro area inflation", "инфлация в еврозоната",
        "еврозоната", "annual inflation in the euro area",
    )),
)

def read_json(key: str):
    path = ROOT / PATHS[key]
    if not path.exists():
        raise RuntimeError(f"Липсва необходимият файл: {PATHS[key]}")
    return json.loads(path.read_text(encoding="utf-8"))

def clean(value, limit=900):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]*>", " ", value)
    return " ".join(value.split())[:limit].strip()

def parse_date(value):
    if not value:
        return None
    try:
        result = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=dt.timezone.utc)
        return result.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

def term_match(text, term):
    text = str(text or "").casefold()
    term = term.casefold()
    tokens = re.findall(r"[a-zа-яё]+", text, flags=re.IGNORECASE)
    if " " in term:
        parts = re.findall(r"[a-zа-яё]+", term, flags=re.IGNORECASE)
        if not parts or len(parts) > len(tokens):
            return False
        return any(
            all(tokens[index + offset].startswith(part) for offset, part in enumerate(parts))
            for index in range(len(tokens) - len(parts) + 1)
        )
    if len(term) <= 4:
        return term in tokens
    return any(token.startswith(term) for token in tokens)

def duplicate_story(left, right):
    stop = {
        "the", "and", "for", "from", "with", "that", "this", "after",
        "before", "into", "over", "under", "about", "their", "they",
        "have", "has", "will", "would", "could", "should", "are", "was",
        "were", "been", "being", "new", "says", "said", "today", "latest",
        "global", "world", "economy", "market", "европейски", "европейския",
        "съюз", "българия", "икономиката", "според",
    }
    left_text = str(left).casefold()
    right_text = str(right).casefold()
    a = set(re.findall(r"[a-zа-яё]{2,}", left_text)) - stop
    b = set(re.findall(r"[a-zа-яё]{2,}", right_text)) - stop
    common = a & b

    # Едно и също събитие може да има различни заглавия в отделни медии.
    if {"eu", "indonesia"}.issubset(common) and common & {"trade", "investment", "agreement", "agreements"}:
        return True
    if {"costa"}.issubset(common) and common & {"budget", "framework", "multiannual"}:
        return True
    if len(common) >= 3 and len(common) / max(1, len(a | b)) >= 0.30:
        return True

    entities = {
        "eu", "china", "ukraine", "russia", "iran", "israel", "america",
        "britain", "germany", "france", "japan", "india", "fed", "ecb",
        "bis", "wto", "imf", "европа", "ецб", "фед", "китай", "русия",
    }
    events = {
        "trade", "investment", "agreement", "agreements", "tariff", "budget",
        "framework", "tax", "monetary", "interest", "inflation", "banking",
        "credit", "debt", "energy", "oil", "gas", "growth", "capital",
        "payments", "бюджет", "търговия", "енергия", "лихви", "инфлация",
    }
    return bool(common & entities) and bool(common & events)


def publisher_key(value):
    """Обединява рубриките на един издател под общо име."""
    text = clean(value, 200).casefold()
    aliases = (
        (("investor.bg", "investor"), "Investor.bg"),
        (("economic.bg",), "Economic.bg"),
        (("deutsche welle", "dw world"), "Deutsche Welle"),
        (("европейска комисия", "european commission"), "Европейска комисия"),
        (("европейска централна банка", "european central bank", "ecb"), "Европейска централна банка"),
        (("евростат", "eurostat"), "Евростат"),
        (("federal reserve",), "Federal Reserve"),
        (("politico",), "POLITICO"),
        (("world trade organization", "wto"), "WTO"),
        (("bank for international settlements", "bis"), "BIS"),
        (("българска народна банка", "bnb"), "БНБ"),
        (("народно събрание", "parliament"), "Народно събрание"),
        (("бта", "bta"), "БТА"),
    )
    for needles, canonical in aliases:
        if any(needle in text for needle in needles):
            return canonical
    return text


def _context_category(title, summary):
    body = (title + " " + summary).casefold()

    # Енергиен пазар: нужен е едновременно европейски обхват и енергийна тема.
    europe_scope = any(term_match(body, term) for term in (
        "европа", "европей", "eu", "europe", "european union",
    ))
    energy_topic = (
        any(term_match(body, term) for term in ("енерг", "energy"))
        and any(term_match(body, term) for term in ("пазар", "market"))
    )
    if europe_scope and energy_topic:
        return "Енергиен пазар на ЕС", 38

    # ЕЦБ: самото споменаване на институцията не е достатъчно.
    ecb_mentioned = any(term_match(body, term) for term in (
        "ецб", "европейска централна банка", "ecb",
    ))
    rate_topic = any(term_match(body, term) for term in (
        "лихв", "повишение на лихвите", "основен лихвен процент",
        "monetary policy", "interest rate", "rate hike", "policy rate",
    ))
    if ecb_mentioned and rate_topic:
        return "Парична политика на ЕЦБ", 35

    # Бюджет на ЕС: трябва да присъстват и ЕС, и бюджетна тема.
    budget_topic = any(term_match(body, term) for term in (
        "бюджет", "budget", "multiannual financial framework",
        "long-term budget",
    ))
    if europe_scope and budget_topic:
        return "Дългосрочен бюджет на ЕС", 32

    # Еврозона: едновременно инфлация и географски обхват на еврозоната.
    if term_match(body, "inflation") and term_match(body, "euro area"):
        return "Инфлация в еврозоната", 29
    if term_match(body, "инфлац") and term_match(body, "еврозон"):
        return "Инфлация в еврозоната", 29

    return None

# Only permanently missing article URLs are excluded. Temporary network errors,
# access restrictions and rate limits are left for the later strict validator.
URL_CHECK_TIMEOUT_SECONDS = 6
URL_CHECK_USER_AGENT = "bgvchisla-editorial-source-check/1.0"
_URL_STATUS_CACHE = {}


def _is_permanently_unavailable(url):
    url = str(url or "")
    if not url.startswith("https://"):
        return True
    if url in _URL_STATUS_CACHE:
        return _URL_STATUS_CACHE[url]

    # Some publishers return 200 for HEAD while the article GET is 404.
    # Use a one-byte ranged GET so the check follows the same HTTP method
    # as the downstream source validator without downloading the article body.
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": URL_CHECK_USER_AGENT,
            "Range": "bytes=0-0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=URL_CHECK_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            response.read(1)
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        # Fail open on transient failures. The generator's strict source
        # validator still decides whether the source can be used.
        _URL_STATUS_CACHE[url] = False
        return False

    unavailable = status in {404, 410}
    _URL_STATUS_CACHE[url] = unavailable
    return unavailable


def _is_recent(item, now, days):
    published = parse_date(item.get("published"))
    if not published:
        return None
    age = now - published
    if age < -dt.timedelta(hours=3) or age > dt.timedelta(days=days):
        return None
    return published

def _data_sources():
    sources, datasets, charts = [], [], []
    definitions = [
        ("D01", "fiscal", "Месечни фискални данни", "Национален статистически институт (НСИ)"),
        ("D02", "economy", "Макроикономически показатели и Евростат", "Евростат"),
        ("D03", "bnb", "Кредитна статистика на БНБ", "Българска народна банка"),
        ("D04", "nssi", "Статистика на НОИ", "Национален осигурителен институт"),
        ("D05", "business", "Бизнес климат на НСИ", "Национален статистически институт (НСИ)"),
    ]
    for sid, key, label, default_publisher in definitions:
        data = read_json(key)
        url = data.get("source_url", "")
        if not url and key == "economy":
            url = "https://ec.europa.eu/eurostat/web/main/data/database"
        if not str(url).startswith("https://"):
            raise RuntimeError("Липсва валиден първичен източник: " + key)
        publisher = data.get("source") or default_publisher
        sources.append({
            "source_id": sid,
            "publisher": clean(publisher),
            "title": label,
            "url": url,
            "updated_at": data.get("updated_at", ""),
        })

        if key in ("fiscal", "bnb"):
            series = data.get("series", [])
            if isinstance(series, dict):
                series = [dict(value, id=series_id) for series_id, value in series.items()]
            facts = [
                {
                    "id": item.get("id"),
                    "label": clean(item.get("title") or item.get("label") or item.get("id")),
                    "unit": item.get("unit"),
                    "points": item.get("points", [])[-6:],
                }
                for item in series[:8]
                if item.get("points")
            ]
        elif key == "economy":
            keep = {
                "gdp_real_growth", "gdp_per_capita_current_eur",
                "employment_rate_20_64", "unemployment_rate_15_74",
                "gdp_pps_index", "exports_goods_mio_eur",
                "imports_goods_mio_eur", "population_total",
            }
            series = data.get("series", [])
            facts = [
                {
                    "id": item.get("id"),
                    "label": item.get("label", item.get("id")),
                    "points": item.get("points", [])[-8:],
                }
                for item in series if item.get("id") in keep
            ]
            for item in series:
                if item.get("id") in keep and len(item.get("points", [])) >= 4:
                    charts.append({
                        "id": item["id"],
                        "label": item.get("label", item["id"]),
                        "unit": item.get("unit", ""),
                        "points": item["points"][-10:],
                    })
        elif key == "nssi":
            facts = data.get("metrics", {})
        else:
            facts = {
                "reference_date": data.get("reference_date"),
                "values": data.get("values", {}),
            }
        datasets.append({
            "source_id": sid,
            "period": data.get("latest_period") or data.get("reference_date"),
            "methodology": clean(data.get("methodology", ""))[:700],
            "facts": facts,
        })
    return sources, datasets, charts

def get_evidence(lane):
    if lane not in {"bulgaria", "world"}:
        raise ValueError("Непознат редакционен фокус: " + str(lane))

    news = read_json("news")
    health = news.get("feed_status", {})
    if health.get("ok", 0) < max(8, (health.get("total", 0) + 1) // 2):
        raise RuntimeError("Достъпността на новинарските източници е под минималния праг.")

    previous_articles = read_json("articles") if (ROOT / PATHS["articles"]).exists() else []
    already_used = {
        str(url).split("#", 1)[0].rstrip("/")
        for article in previous_articles[-12:]
        for url in article.get("source_urls", [])
    }

    now = dt.datetime.now(dt.timezone.utc)
    max_age_days = 7 if lane == "world" else 10
    domestic_rank, context_rank, world_rank = [], [], []

    for item in news.get("items", []):
        section = item.get("section")
        url = str(item.get("url", ""))
        if not url.startswith("https://"):
            continue
        if url.split("#", 1)[0].rstrip("/") in already_used:
            continue

        published = _is_recent(item, now, max_age_days)
        if not published:
            continue

        title = clean(item.get("title", ""), 400)
        summary = clean(item.get("summary", ""), 900)
        title_l = title.casefold()
        body = (title_l + " " + summary.casefold()).strip()
        publisher = clean(item.get("source", "Източник"), 160)
        feed_id = item.get("feed_id", "")

        if lane == "world":
            if section != "europe":
                continue
            title_hits = [term for term in WORLD_TERMS if term_match(title_l, term)]
            if not title_hits:
                continue
            score = sum(4 if term_match(title_l, term) else 1 for term in WORLD_TERMS if term_match(body, term))
            world_rank.append((score, published, item, publisher, title, summary))
            continue

        if section == "bulgaria":
            title_hits = [term for term in BG_CORE_TERMS if term_match(title_l, term)]
            if not title_hits:
                continue
            collector_coin = (
                "монет" in body
                and any(term in body for term in ("колекционер", "емисия", "продавани на каса"))
            )
            if collector_coin:
                continue
            foreign_focus = any(term_match(title_l, term) for term in FOREIGN_FOCUS_TERMS)
            domestic_focus = any(term_match(body, term) for term in DOMESTIC_MARKERS)
            if foreign_focus and not domestic_focus:
                continue
            score = sum(6 if term_match(title_l, term) else 1 for term in BG_CORE_TERMS if term_match(body, term))
            if domestic_focus:
                score += 5
            domestic_rank.append((score, published, item, publisher, title, summary))
        elif section == "europe":
            context = _context_category(title, summary)
            if context:
                label, score = context
                context_rank.append((score, published, item, publisher, title, summary, label))

    selected = []
    publishers = set()

    if lane == "bulgaria":
        domestic_rank.sort(key=lambda row: (row[0], row[1]), reverse=True)
        context_rank.sort(key=lambda row: (row[0], row[1]), reverse=True)

        # Най-много три вътрешни публикации от един издател, за да не се
        # превръща един новинарски поток в привидно независимо покритие.
        domestic_counts = {}
        for score, published, item, publisher, title, summary in domestic_rank:
            if domestic_counts.get(publisher_key(publisher), 0) >= 3:
                continue
            if _is_permanently_unavailable(item.get("url")):
                print(
                    "ИЗКЛЮЧЕН НЕДОСТЪПЕН ИЗТОЧНИК (HTTP 404/410) |",
                    publisher,
                    "|",
                    title,
                    "|",
                    item.get("url", ""),
                )
                continue
            domestic_counts[publisher_key(publisher)] = domestic_counts.get(publisher_key(publisher), 0) + 1
            selected.append({
                "kind": "domestic",
                "score": score,
                "published_at": published,
                "item": item,
                "publisher": publisher,
                "title": title,
                "summary": summary,
                "context_label": "",
            })
            publishers.add(publisher_key(publisher))
            if sum(1 for row in selected if row["kind"] == "domestic") >= 3:
                break

        context_publishers = set()
        context_labels = set()
        for score, published, item, publisher, title, summary, label in context_rank:
            publisher_id = publisher_key(publisher)
            if publisher_id in context_publishers or label in context_labels:
                continue
            if _is_permanently_unavailable(item.get("url")):
                print(
                    "ИЗКЛЮЧЕН НЕДОСТЪПЕН КОНТЕКСТЕН ИЗТОЧНИК (HTTP 404/410) |",
                    publisher,
                    "|",
                    title,
                    "|",
                    item.get("url", ""),
                )
                continue
            selected.append({
                "kind": "context",
                "score": score,
                "published_at": published,
                "item": item,
                "publisher": publisher,
                "title": title,
                "summary": summary,
                "context_label": label,
            })
            context_publishers.add(publisher_id)
            context_labels.add(label)
            publishers.add(publisher_id)
            if len(context_publishers) >= 2:
                break

        domestic_count = sum(1 for row in selected if row["kind"] == "domestic")
        context_count = sum(1 for row in selected if row["kind"] == "context")
        if domestic_count < 2 or context_count < 1 or len(selected) < 4 or len(publishers) < 2:
            raise RuntimeError(
                "Недостатъчна редакционна основа за анализ на България: "
                f"{domestic_count} вътрешни материала, {context_count} международни контекстни материала, "
                f"{len(publishers)} издатели. Анализът се задържа."
            )
        selected.sort(key=lambda row: (row["score"], row["published_at"]), reverse=True)
    else:
        world_rank.sort(key=lambda row: (row[0], row[1]), reverse=True)
        counts = {}
        picked = []
        for score, published, item, publisher, title, summary in world_rank:
            publisher_id = publisher_key(publisher)
            if counts.get(publisher_id, 0) >= 2:
                continue
            if _is_permanently_unavailable(item.get("url")):
                print(
                    "ИЗКЛЮЧЕН НЕДОСТЪПЕН СВЕТОВЕН ИЗТОЧНИК (HTTP 404/410) |",
                    publisher,
                    "|",
                    title,
                    "|",
                    item.get("url", ""),
                )
                continue
            if any(duplicate_story(title + " " + summary, row["title"] + " " + row["summary"]) for row in picked):
                continue
            picked.append({
                "kind": "world",
                "score": score,
                "published_at": published,
                "item": item,
                "publisher": publisher,
                "title": title,
                "summary": summary,
                "context_label": "",
            })
            counts[publisher_id] = counts.get(publisher_id, 0) + 1
            publishers.add(publisher_id)
            if len(picked) >= 8:
                break
        if len(picked) < 4 or len(publishers) < 3:
            raise RuntimeError(
                "Недостатъчно актуални световни материали: "
                f"{len(picked)} публикации от {len(publishers)} издатели. Анализът се задържа."
            )
        selected = picked

    items = []
    for row in selected:
        number = len(items) + 1
        relevance = {
            "domestic": "Български икономически материал",
            "context": "Международен контекст за България: " + row["context_label"],
            "world": "Световна икономика и финансови пазари",
        }[row["kind"]]
        items.append({
            "source_id": f"N{number:02d}",
            "publisher": row["publisher"],
            "title": row["title"],
            "url": row["item"]["url"],
            "published": row["published_at"].isoformat(),
            "summary": row["summary"][:650],
            "editorial_role": relevance,
        })

    sources, datasets, charts = [], [], []
    if lane == "bulgaria":
        sources, datasets, charts = _data_sources()
    else:
        sources = []
        datasets = []
        charts = []

    return {
        "lane": lane,
        "generated_at": now.isoformat(),
        "feed_health": health,
        "sources": sources + items,
        "datasets": datasets,
        "chart_candidates": charts,
    }

def main():
    parser = argparse.ArgumentParser(description="Безплатен одит на подбраните редакционни източници.")
    parser.add_argument("--lane", choices=("bulgaria", "world"), required=True)
    args = parser.parse_args()
    pack = get_evidence(args.lane)
    print(f"Фокус: {args.lane}; източници общо: {len(pack['sources'])}; новинарски материали: {len(pack['sources']) - (5 if args.lane == 'bulgaria' else 0)}")
    for source in pack["sources"]:
        if source["source_id"].startswith("N"):
            print(
                "ПОДБРАН МАТЕРИАЛ |",
                source.get("editorial_role", ""),
                "|",
                source.get("publisher", ""),
                "|",
                source.get("published", ""),
                "|",
                source.get("title", ""),
                "|",
                source.get("url", ""),
            )

if __name__ == "__main__":
    main()
