#!/usr/bin/env python3
"""Fetch approved institutional RSS/Atom headlines for bgvchisla.com.

Only titles, short feed descriptions, source names, dates and canonical links are
stored. Article bodies and images are never copied.
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("news.json")
MAX_BYTES = 1_000_000
TIMEOUT = 20
MAX_PER_FEED = 35
USER_AGENT = "bgvchisla-news-aggregator/1.0 (+https://bgvchisla.com)"
FEEDS = [
    {
        "id": "eurostat-bg",
        "section": "bulgaria",
        "name": "Евростат",
        "url": "https://ec.europa.eu/eurostat/en/search?_estatsearchportlet_WAR_estatsearchportlet_collection=CAT_EURNEW&_estatsearchportlet_WAR_estatsearchportlet_theme=PER_GENSTA&p_p_id=estatsearchportlet_WAR_estatsearchportlet&p_p_lifecycle=2&p_p_mode=view&p_p_resource_id=atom&p_p_state=maximized",
        "allowed_hosts": ["ec.europa.eu"],
        "keywords": ["bulgaria", "bulgarian", "българ", "bulgarie"],
    },
    {
        "id": "ecb-press",
        "section": "europe",
        "name": "Европейска централна банка",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "allowed_hosts": ["www.ecb.europa.eu", "ecb.europa.eu"],
        "keywords": [],
    },
]

class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)

def clean_text(value, limit=320):
    parser = TextOnly()
    try:
        parser.feed(value or "")
        text = " ".join(" ".join(parser.parts).split())
    except Exception:
        text = re.sub(r"<[^>]*>", " ", value or "")
    return html.unescape(text)[:limit].strip()

def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()

def child_text(node, names):
    for child in list(node):
        if local_name(child.tag) in names:
            if local_name(child.tag) == "link":
                href = child.attrib.get("href")
                if href:
                    return href.strip()
            return "".join(child.itertext()).strip()
    return ""

def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def valid_url(url, hosts):
    try:
        p = urllib.parse.urlparse(url)
        return p.scheme == "https" and (p.hostname or "").lower() in hosts
    except Exception:
        return False

def fetch(feed):
    url = feed["url"]
    if not valid_url(url, feed["allowed_hosts"]):
        raise ValueError("Feed URL is not on the HTTPS host allowlist")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        final_url = response.geturl()
        if not valid_url(final_url, feed["allowed_hosts"]):
            raise ValueError("Feed redirected outside its host allowlist")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Feed exceeds the 1 MB size limit")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("DTD/entity declarations are not accepted")
    root = ET.fromstring(raw)
    rows = []
    for node in root.iter():
        if local_name(node.tag) not in ("item", "entry"):
            continue
        title = clean_text(child_text(node, {"title"}), 220)
        link = child_text(node, {"link"})
        if not link:
            link = child_text(node, {"guid", "id"})
        if link and not urllib.parse.urlparse(link).scheme:
            link = urllib.parse.urljoin(final_url, link)
        if not title or not valid_url(link, feed["allowed_hosts"]):
            continue
        description = clean_text(child_text(node, {"description", "summary", "content"}), 260)
        date = parse_date(child_text(node, {"pubdate", "published", "updated", "date", "issued"}))
        if feed["keywords"]:
            haystack = (title + " " + description).casefold()
            if not any(k.casefold() in haystack for k in feed["keywords"]):
                continue
        rows.append({
            "section": feed["section"], "source": feed["name"],
            "title": title, "summary": description, "url": link,
            "published": date, "feed_id": feed["id"],
        })
        if len(rows) >= MAX_PER_FEED:
            break
    return rows

def main():
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    all_items = []
    failures = []
    for feed in FEEDS:
        try:
            all_items.extend(fetch(feed))
        except Exception as exc:
            failures.append({"feed": feed["id"], "error": str(exc)[:180]})
    if failures and not all_items and previous.get("items"):
        print("All feeds failed; preserving previous valid news.json")
        return
    dedup = {}
    for item in all_items:
        key = item["url"].split("#", 1)[0].rstrip("/")
        if key not in dedup or (item["published"] or "") > (dedup[key]["published"] or ""):
            dedup[key] = item
    items = sorted(dedup.values(), key=lambda x: x["published"] or "", reverse=True)[:70]
    result = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "feed_status": {
            "ok": len(FEEDS) - len(failures),
            "total": len(FEEDS),
            "failures": failures,
        },
        "notice": "Показваме заглавия и кратки описания от RSS/Atom емисиите. Пълният материал се чете на сайта на източника."
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    print(f"Saved {len(items)} items; {len(failures)} feed failures")

if __name__ == "__main__":
    main()
