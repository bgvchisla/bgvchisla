#!/usr/bin/env python3
"""Publish generated analyses in the website's current directory/registry format."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_URL = "https://bgvchisla.com"


def modernize_page(page: str, slug: str, title: str, summary: str) -> str:
    canonical_url = f"{BASE_URL}/analizi/{slug}/"
    canonical = f'<link rel="canonical" href="{canonical_url}">'
    page, count = re.subn(r'<link rel="canonical" href="[^"]*">', lambda _: canonical, page, count=1)
    if count != 1:
        raise RuntimeError("Не е намерен еднозначен canonical елемент.")

    byline = re.search(
        r'<div class="meta">Редакция БЪЛГАРИЯ В ЧИСЛА\s*/\s*([^<]+)</div>',
        page,
        flags=re.I,
    )
    if not byline:
        raise RuntimeError("Липсва авторската позиция за модернизиране на статията.")
    byline_html = (
        '<div class="byline">Редакция БЪЛГАРИЯ В ЧИСЛА / '
        + html.escape(byline.group(1).strip())
        + "</div>"
    )
    page = page[:byline.start()] + byline_html + page[byline.end():]

    if 'property="og:title"' not in page or 'property="og:description"' not in page:
        head_end = page.find("</head>")
        if head_end < 0:
            raise RuntimeError("Липсва затварящ head елемент.")
        social = (
            f'<meta property="og:title" content="{html.escape(title, quote=True)}">\n'
            f'<meta property="og:description" content="{html.escape(summary, quote=True)}">\n'
        )
        page = page[:head_end] + social + page[head_end:]

    css = """
:root{--navy:#24384f;--blue:#315f91;--risk:#b64b45}
.byline{color:#718096;font-size:.8rem;margin:12px 0 20px}
@media(max-width:640px){main{padding-left:14px;padding-right:14px}h1{font-size:2rem}}
"""
    if "</style>" not in page:
        raise RuntimeError("Липсва style блок.")
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
        raise RuntimeError("Статията не покрива договора за публикация: " + ", ".join(missing))
    return page


def update_archive(path: Path, slug: str, row: dict[str, Any], date_label: str) -> None:
    archive = path.read_text(encoding="utf-8")
    href = f'/analizi/{slug}/'
    if href in archive:
        raise RuntimeError("Статията вече присъства в архива.")
    match = re.search(r'(<div class="grid">)([\s\S]*?)(</div>)', archive, flags=re.I)
    if not match or len(re.findall(r'<div class="grid">', archive, flags=re.I)) != 1:
        raise RuntimeError("Не е намерена еднозначна grid секция в архива.")

    lane_label = "БЪЛГАРИЯ · ИКОНОМИКА" if row["lane"] == "bulgaria" else "СВЯТ · ИКОНОМИКА"
    card = (
        f'<a class="article-card" href="{href}">'
        f'<span class="article-meta">{lane_label} · {html.escape(date_label)}</span>'
        f'<strong>{html.escape(row["title"])}</strong>'
        f'<span class="article-excerpt">{html.escape(row["summary"])}</span>'
        '<span class="article-read">КЪМ АНАЛИЗА ↗</span>'
        "</a>"
    )
    updated = archive[:match.start()] + match.group(1) + "\n" + card + match.group(2) + match.group(3) + archive[match.end():]
    path.write_text(updated, encoding="utf-8")


def update_sitemap(path: Path, canonical_url: str) -> None:
    sitemap = path.read_text(encoding="utf-8")
    if canonical_url in sitemap:
        raise RuntimeError("Canonical URL вече присъства в sitemap.xml.")
    if "</urlset>" not in sitemap:
        raise RuntimeError("Липсва затварящ urlset елемент.")
    sitemap = sitemap.replace(
        "</urlset>",
        f"  <url><loc>{html.escape(canonical_url)}</loc></url>\n</urlset>",
        1,
    )
    path.write_text(sitemap, encoding="utf-8")


def publish_article(
    root: Path,
    article: dict[str, Any],
    lane: str,
    now: datetime,
    date_label: str,
    rendered_page: str,
    slug: str,
) -> Path:
    if lane not in {"bulgaria", "world"}:
        raise ValueError("Непознато редакционно направление.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise RuntimeError("Невалиден slug.")
    analysis_dir = root / "analizi"
    page_path = analysis_dir / slug / "index.html"
    registry_path = analysis_dir / "articles.json"
    archive_path = analysis_dir / "index.html"
    sitemap_path = root / "sitemap.xml"
    if page_path.exists():
        raise RuntimeError("Отказвам презапис на съществуваща статия.")

    source_index = article.get("_src", {})
    source_urls = []
    for source_id in article.get("used_source_ids", []):
        source = source_index.get(source_id)
        url = str((source or {}).get("url", ""))
        if not url.startswith("https://"):
            raise RuntimeError(f"Невалиден използван първоизточник: {source_id}")
        source_urls.append(url)
    source_urls = sorted(set(source_urls))
    if len(source_urls) < 4:
        raise RuntimeError("Статията трябва да цитира поне четири различни първоизточника.")

    page = modernize_page(rendered_page, slug, str(article["title"]), str(article["summary"]))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, list):
        raise RuntimeError("Регистърът на анализите не е JSON списък.")
    if any(str(item.get("slug", "")) == slug for item in registry):
        raise RuntimeError("Slug вече присъства в регистъра.")

    row = {
        "slug": slug,
        "title": str(article["title"]),
        "summary": str(article["summary"]),
        "published_at": now.date().isoformat(),
        "lane": lane,
        "source_urls": source_urls,
    }
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page, encoding="utf-8")
    registry.insert(0, row)
    registry.sort(
        key=lambda item: str(item.get("published_at") or item.get("date") or ""),
        reverse=True,
    )
    registry_path.write_text(json.dumps(registry[:100], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_archive(archive_path, slug, row, date_label)
    update_sitemap(sitemap_path, f"{BASE_URL}/analizi/{slug}/")
    print(
        f"Създадена е статията /analizi/{slug}/; "
        f"думи={article.get('_words', 0)}; източници={len(source_urls)}."
    )
    return page_path
