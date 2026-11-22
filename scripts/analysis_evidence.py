#!/usr/bin/env python3
"""Строг редакционен подбор на доказателства за автоматизираните анализи."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
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
    ("Парична политика на ЕЦБ", 35, (
        "ецб", "европейска централна банка", "ecb",
        "monetary policy", "interest rates",
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
    if " " in term:
        pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
        return re.search(pattern, text, flags=re.UNICODE) is not None
    tokens = re.findall(r"[a-zа-яё]+", text, flags=re.IGNORECASE)
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
    a = set(re.findall(r"[a-zа-яё]{3,}", str(left).casefold())) - stop
    b = set(re.findall(r"[a-zа-яё]{3,}", str(right).casefold())) - stop
    common = a & b
    if len(common) >= 3 and len(common) / max(1, len(a | b)) >= 0.30:
        return True
    entities = {
        "eu", "china", "ukraine", "russia", "iran", "israel", "america",
        "britain", "germany", "france", "japan", "india", "fed", "ecb",
        "bis", "wto", "imf", "европа", "ецб", "фед", "китай", "русия",
    }
    events = {
        "trade", "investment", "agreement", "tariff", "budget", "framework",
        "tax", "monetary", "interest", "inflation", "banking", "credit",
        "debt", "energy", "oil", "gas", "growth", "capital", "payments",
        "бюджет", "търговия", "енергия", "лихви", "инфлация",
    }
    return bool(common & entities) and bool(common & events)

def _context_category(title, summary):
    body = (title + " " + summary).casefold()
    for label, score, terms in CONTEXT_RULES:
        if any(term_match(body, term) for term in terms):
            return label, score
    return None

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
            if domestic_counts.get(publisher, 0) >= 3:
                continue
            domestic_counts[publisher] = domestic_counts.get(publisher, 0) + 1
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
            publishers.add(publisher)
            if sum(1 for row in selected if row["kind"] == "domestic") >= 3:
                break

        context_publishers = set()
        context_labels = set()
        for score, published, item, publisher, title, summary, label in context_rank:
            if publisher in context_publishers or label in context_labels:
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
            context_publishers.add(publisher)
            context_labels.add(label)
            publishers.add(publisher)
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
            if counts.get(publisher, 0) >= 2:
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
            counts[publisher] = counts.get(publisher, 0) + 1
            publishers.add(publisher)
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
