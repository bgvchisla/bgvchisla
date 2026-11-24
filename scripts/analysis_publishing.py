#!/usr/bin/env python3
"""Publish a generated article using the site's current registry and URL structure."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_URL = "https://bgvchisla.com"


def _modernize_page(
    page: str,
    slug: str,
    title: str,
    summary: str,
    canonical_url: str,
) -> str:
    """Adapt the legacy renderer output to the current publication contract."""
    canonical = f'<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">'
    page, count = re.subn(
        r'<link rel="canonical" href="[^"]*">',
        lambda _match: canonical,
        page,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Не е намерен еднозначен canonical елемент в статията.")

    byline_match = re.search(
        r'<div class="meta">Редакция БЪЛГАРИЯ В ЧИСЛА\s*/\s*([^<]+)</div>',
        page,
        flags=re.I,
    )
    if not byline_match:
        raise RuntimeError("Липсва метаданни за авторската позиция в статията.")
    byline = (
        '<div class="byline">Редакция БЪЛГАРИЯ В ЧИСЛА / '
        + html.escape(byline_match.group(1).strip())
        + "</div>"
    )
    page = page[:byline_match.start()] + byline + page[byline_match.end():]

    if 'property="og:title"' not in page or 'property="og:description"' not in page:
        open_head = page.find("</head>")
        if open_head < 0:
            raise RuntimeError("Липсва затварящ head елемент.")
        social = (
            f'<meta property="og:title" content="{html.escape(title, quote=True)}">\n'
            f'<meta property="og:description" content="{html.escape(summary, quote=True)}">\n'
        )
        page = page[:open_head] + social + page[open_head:]

    css = """
:root{--navy:#24384f;--blue:#315f91;--risk:#b64b45}
.byline{color:#718096;font-size:.8rem;margin:12px 0 20px}
@media(max-width:640px){main{padding-left:14px;padding-right:14px}h1{font-size:2rem}}
"""
    if "</style>" not in page:
        raise RuntimeError("Липсва style блок в генерираната статия.")
    page = page.replace("</style>", css + "\n</style>", 1)

    required = (
        '<html lang="bg">',
        canonical,
        'property="og:title"',
        'property="og:description"',
        '<div class="byline">',
        "--navy:#24384f",
        "--blue:#315f91",
        "--risk:#b64b45",
        "@media(max-width:640px)",
        "<article>",
        "</article>",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError("Генерираната статия не покрива HTML договора: " + ", ".join(missing))
    return page


def _update_archive(archive_path: Path, slug: str, row: dict[str, Any], date_label: str) -> None:
    archive = archive_path.read_text(encoding="utf-8")
    href = f'/analizi/{slug}/'
    if href in archive:
        raise RuntimeError("Статията вече присъства в редакционния архив.")

    pattern = re.compile(r'(<div class="grid">)([\s\S]*?)(</div>)', flags=re.I)
    matches = list(pattern.finditer(archive))
    if len(matches) != 1:
        raise RuntimeError("Архивът трябва да съдържа точно една grid секция.")

    lane_label = "БЪЛГАРИЯ · ИКОНОМИКА" if row["lane"] == "bulgaria" else "СВЯТ · ИКОНОМИКА"
    card = (
        f'<a class="article-card" href="{href}">'
        f'<span class="article-meta">{lane_label} · {html.escape(date_label)}</span>'
        f'<strong>{html.escape(row["title"])}</strong>'
        f'<span class="article-excerpt">{html.escape(row["summary"])}</span>'
        '<span class="article-read">КЪМ АНАЛИЗА ↗</span>'
        "</a>"
    )
    match = matches[0]
    replacement = match.group(1) + "\n" + card + match.group(2) + match.group(3)
    archive = archive[:match.start()] + replacement + archive[match.end():]
    archive_path.write_text(archive, encoding="utf-8")


def _update_sitemap(sitemap_path: Path, canonical_url: str) -> None:
    sitemap = sitemap_path.read_text(encoding="utf-8")
    if canonical_url in sitemap:
        raise RuntimeError("Canonical URL вече присъства в sitemap.xml.")
    if "</urlset>" not in sitemap:
        raise RuntimeError("Липсва затварящ urlset елемент в sitemap.xml.")
    entry = f"  <url><loc>{html.escape(canonical_url)}</loc></url>\n"
    sitemap_path.write_text(sitemap.replace("</urlset>", entry + "</urlset>", 1), encoding="utf-8")


def publish_article(
    root: Path,
    article: dict[str, Any],
    lane: str,
    now: datetime,
    date_label: str,
    rendered_page: str,
    slug: str,
) -> Path:
    """Write page, current article registry, archive card and sitemap entry."""
    if lane not in {"bulgaria", "world"}:
        raise ValueError("Непознато редакционно направление.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise RuntimeError("Невалиден slug за публикуване.")

    analysis_dir = root / "analizi"
    page_path = analysis_dir / slug / "index.html"
    registry_path = analysis_dir / "articles.json"
    archive_path = analysis_dir / "index.html"
    sitemap_path = root / "sitemap.xml"

    if page_path.exists():
        raise RuntimeError("Отказвам презапис на съществуваща статия.")

    sources = article.get("_src", {})
    used_ids = article.get("used_source_ids", [])
    source_urls = []
    for source_id in used_ids:
        source = sources.get(source_id)
        if not source or not str(source.get("url", "")).startswith("https://"):
            raise RuntimeError("Статията съдържа невалиден използван първоизточник.")
        source_urls.append(source["url"])
    if len(set(source_urls)) < 4:
        raise RuntimeError("Статията трябва да съдържа поне четири валидни първоизточника.")

    canonical_url = f"{BASE_URL}/analizi/{slug}/"
    page = _modernize_page(
        rendered_page,
        slug,
        str(article["title"]),
        str(article["summary"]),
        canonical_url,
    )

    existing = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(existing, list):
        raise RuntimeError("Регистърът на анализите трябва да бъде JSON списък.")
    if any(str(item.get("slug", "")) == slug for item in existing):
        raise RuntimeError("Slug вече присъства в регистъра на анализите.")

    row = {
        "slug": slug,
        "title": str(article["title"]),
        "summary": str(article["summary"]),
        "published_at": now.date().isoformat(),
        "lane": lane,
        "source_urls": sorted(set(source_urls)),
    }

    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page, encoding="utf-8")
    existing.insert(0, row)
    existing.sort(
        key=lambda item: str(item.get("published_at") or item.get("date") or ""),
        reverse=True,
    )
    registry_path.write_text(
        json.dumps(existing[:100], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _update_archive(archive_path, slug, row, date_label)
    _update_sitemap(sitemap_path, canonical_url)
    print(
        f"Създадена е статията /analizi/{slug}/; "
        f"думи={article.get('_words', 0)}; източници={len(set(source_urls))}."
    )
    return page_path
