#!/usr/bin/env python3
"""Collect, score, diversify and group RSS/Atom headlines for bgvchisla.com.

Only titles, short feed descriptions, source names, dates and canonical links are
stored. Article bodies and images are never copied. Ranking is significance-first,
with recency as the secondary sort key.
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("news.json")
MAX_BYTES = 1_000_000
TIMEOUT = 20
MAX_PER_FEED = 35
MAX_ITEM_AGE_DAYS = 10
MAX_LEAD_AGE_HOURS = 18
FUTURE_DATE_TOLERANCE_HOURS = 24
USER_AGENT = "bgvchisla-news-aggregator/1.0 (+https://bgvchisla.com)"
FEEDS = [
    {
        "id": "parliament-news",
        "section": "bulgaria",
        "name": "Народно събрание",
        "url": "https://www.parliament.bg/bg/news",
        "mode": "html",
        "allowed_hosts": ["www.parliament.bg", "parliament.bg"],
        "keywords": [],
    },
    {
        "id": "bnb-news",
        "section": "bulgaria",
        "name": "Българска народна банка",
        "url": "https://www.bnb.bg/AboutUs/PressOffice/POPressReleases/POPRDate/",
        "mode": "html",
        "allowed_hosts": ["www.bnb.bg", "bnb.bg"],
        "keywords": [],
    },
    {
        "id": "investor-bg",
        "section": "bulgaria",
        "name": "Investor.bg – България",
        "url": "https://www.investor.bg/rss/c/5-balgariya",
        "allowed_hosts": ["www.investor.bg", "investor.bg"],
        "keywords": [],
    },
    {
        "id": "investor-economy",
        "section": "bulgaria",
        "name": "Investor.bg – Икономика и политика",
        "url": "https://www.investor.bg/rss/c/514-ikonomika-i-politika",
        "allowed_hosts": ["www.investor.bg", "investor.bg"],
        "keywords": [],
    },
    {
        "id": "investor-finance",
        "section": "bulgaria",
        "name": "Investor.bg – Финанси",
        "url": "https://www.investor.bg/rss/c/536-finansi",
        "allowed_hosts": ["www.investor.bg", "investor.bg"],
        "keywords": [],
    },
    {
        "id": "bta-bulgaria",
        "section": "bulgaria",
        "name": "БТА",
        "url": "https://www.bta.bg/bg/news/bulgaria/rss",
        "allowed_hosts": ["www.bta.bg", "bta.bg"],
        "keywords": [],
    },
    {
        "id": "economic-bg",
        "section": "bulgaria",
        "name": "Economic.bg",
        "url": "https://www.economic.bg/bg/rss.xml",
        "allowed_hosts": ["www.economic.bg", "economic.bg"],
        "keywords": [],
    },
    {
        "id": "ecb-press",
        "section": "europe",
        "name": "Европейска централна банка",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "allowed_hosts": ["www.ecb.europa.eu", "ecb.europa.eu"],
        "keywords": [],
    },
    {
        "id": "commission-press",
        "section": "europe",
        "name": "Европейска комисия",
        "url": "https://ec.europa.eu/commission/presscorner/api/rss?language=en",
        "allowed_hosts": ["ec.europa.eu"],
        "keywords": [],
    },
    {
        "id": "council-press",
        "section": "europe",
        "name": "Съвет на Европейския съюз",
        "url": "https://www.consilium.europa.eu/en/rss/pressreleases.ashx/",
        "allowed_hosts": ["www.consilium.europa.eu", "consilium.europa.eu"],
        "keywords": [],
    },
    {
        "id": "eurostat-news",
        "section": "europe",
        "name": "Евростат",
        "url": "https://ec.europa.eu/eurostat/en/search?_estatsearchportlet_WAR_estatsearchportlet_collection=CAT_PREREL&p_p_id=estatsearchportlet_WAR_estatsearchportlet&p_p_lifecycle=2&p_p_mode=view&p_p_resource_id=atom&p_p_state=maximized",
        "allowed_hosts": ["ec.europa.eu"],
        "keywords": [],
    },
    {
        "id": "un-geneva-press",
        "section": "europe",
        "name": "ООН – Женева",
        "url": "https://www.ungeneva.org/news-media/press-items-list/rss.xml",
        "allowed_hosts": ["www.ungeneva.org", "ungeneva.org"],
        "keywords": [],
    },
    {
        "id": "bbc-world",
        "section": "europe",
        "name": "BBC News – Свят",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "allowed_hosts": ["feeds.bbci.co.uk", "www.bbc.co.uk", "bbc.co.uk"],
        "keywords": [],
    },
    {
        "id": "dw-world",
        "section": "europe",
        "name": "Deutsche Welle",
        "url": "https://rss.dw.com/rdf/rss-en-all",
        "allowed_hosts": ["rss.dw.com", "www.dw.com", "dw.com"],
        "keywords": [],
    },
    {
        "id": "euronews",
        "section": "europe",
        "name": "Euronews",
        "url": "https://www.euronews.com/rss?level=theme&name=news",
        "allowed_hosts": ["www.euronews.com", "euronews.com"],
        "keywords": [],
    },
    {
        "id": "guardian-world",
        "section": "europe",
        "name": "The Guardian – World",
        "url": "https://www.theguardian.com/world/rss",
        "allowed_hosts": ["www.theguardian.com", "theguardian.com"],
        "keywords": [],
    },
    {
        "id": "politico-europe",
        "section": "europe",
        "name": "POLITICO Europe",
        "url": "https://www.politico.eu/feed/",
        "allowed_hosts": ["www.politico.eu", "politico.eu"],
        "keywords": [],
    },
    {
        "id": "federal-reserve",
        "section": "europe",
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "allowed_hosts": ["www.federalreserve.gov"],
        "keywords": ["monetary", "FOMC", "financial", "bank", "credit", "interest rate", "reserve balances", "inflation", "capital", "liquidity"],
    },
    {
        "id": "bis-press",
        "section": "europe",
        "name": "Bank for International Settlements (BIS)",
        "url": "https://www.bis.org/doclist/all_pressrels.rss",
        "allowed_hosts": ["www.bis.org", "bis.org"],
        "keywords": ["banking", "financial", "payments", "capital", "credit", "liquidity", "monetary", "risk", "economic", "growth"],
    },
    {
        "id": "bis-research",
        "section": "europe",
        "name": "BIS Research",
        "url": "https://www.bis.org/doclist/bis_fsi_publs.rss",
        "allowed_hosts": ["www.bis.org", "bis.org"],
        "keywords": ["economic", "growth", "capital", "productivity", "digital payments", "inflation", "credit", "banking", "trade", "employment", "financial"],
    },
    {
        "id": "wto-news",
        "section": "europe",
        "name": "World Trade Organization (WTO)",
        "url": "https://www.wto.org/library/rss/latest_news_e.xml",
        "allowed_hosts": ["www.wto.org", "wto.org"],
        "keywords": ["trade", "tariff", "export", "import", "agreement", "supply chain", "services", "economic", "market", "investment"],
    },
]

class LinkFinder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.events = []
        self.href = None
        self.parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "a":
            self.href = attrs.get("href")
            self.parts = [attrs.get("title", ""), attrs.get("aria-label", "")]
        elif self.href is not None and tag.lower() == "img":
            self.parts.append(attrs.get("alt", ""))
    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)
        elif data.strip():
            self.events.append(("text", data.strip()))
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            label = " ".join(" ".join(self.parts).split())
            self.links.append((self.href, label))
            self.events.append(("link", self.href, label))
            self.href = None
            self.parts = []

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

def fetch_parliament_api(feed):
    # The official event-list endpoint returns a collection of recent events
    # linked to news records. Deduplicate bilingual rows by M_News_id.
    api_url = "https://www.parliament.bg/api/v1/event-list/bg/10"
    if not valid_url(api_url, feed["allowed_hosts"]):
        raise ValueError("Parliament API URL is not on the HTTPS host allowlist")
    req = urllib.request.Request(api_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        final_url = response.geturl()
        if not valid_url(final_url, feed["allowed_hosts"]):
            raise ValueError("Parliament API redirected outside its host allowlist")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Parliament API response exceeds the 1 MB size limit")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Unexpected Parliament event-list response format")
    rows = []
    seen_ids = set()
    for record in payload:
        if not isinstance(record, dict):
            continue
        news_id = record.get("M_News_id")
        if not str(news_id or "").isdigit():
            continue
        news_id = int(news_id)
        if news_id in seen_ids:
            continue
        seen_ids.add(news_id)
        title = clean_text(str(record.get("M_NewsL_title") or ""), 400)
        published = parse_date(str(record.get("G_Gal_E_date") or record.get("M_News_date") or ""))
        # The API includes localized duplicates; keep Bulgarian-language headlines.
        if not title or not re.search(r"[А-Яа-я]", title):
            continue
        article_url = "https://www.parliament.bg/bg/news/" + str(news_id)
        rows.append({
            "section": feed["section"], "source": feed["name"],
            "title": title, "summary": "", "url": article_url,
            "published": published, "feed_id": feed["id"],
        })
        if len(rows) >= MAX_PER_FEED:
            break
    if not rows:
        raise ValueError("Parliament event-list API returned no usable news records")
    return rows

def fetch_html_news(feed):
    page_url = feed["url"]
    if not valid_url(page_url, feed["allowed_hosts"]):
        raise ValueError("HTML news URL is not on the HTTPS host allowlist")
    req = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        final_url = response.geturl()
        if not valid_url(final_url, feed["allowed_hosts"]):
            raise ValueError("HTML news page redirected outside its host allowlist")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("HTML news page exceeds the 1 MB size limit")
    parser = LinkFinder()
    parser.feed(raw.decode("utf-8", errors="replace"))
    rows = []
    if feed["id"] == "bnb-news":
        pending = None
        events = parser.events + [("end",)]
        for event in events:
            if event[0] == "link":
                if pending:
                    href, date_text, parts = pending
                    title = clean_text(" ".join(parts), 400)
                    match = re.fullmatch(r"([0-9]{2})\.([0-9]{2})\.([0-9]{4})", date_text)
                    url = urllib.parse.urljoin(final_url, href)
                    if title and match and valid_url(url, feed["allowed_hosts"]):
                        day, month, year = match.groups()
                        rows.append({"section": feed["section"], "source": feed["name"], "title": title,
                                     "summary": "", "url": url, "published": f"{year}-{month}-{day}T00:00:00+00:00",
                                     "feed_id": feed["id"]})
                href, label = event[1], event[2]
                pending = [href, label, []] if re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", label) else None
            elif event[0] == "text" and pending:
                pending[2].append(event[1])
            elif event[0] == "end" and pending:
                href, date_text, parts = pending
                title = clean_text(" ".join(parts), 400)
                match = re.fullmatch(r"([0-9]{2})\.([0-9]{2})\.([0-9]{4})", date_text)
                url = urllib.parse.urljoin(final_url, href)
                if title and match and valid_url(url, feed["allowed_hosts"]):
                    day, month, year = match.groups()
                    rows.append({"section": feed["section"], "source": feed["name"], "title": title,
                                 "summary": "", "url": url, "published": f"{year}-{month}-{day}T00:00:00+00:00",
                                 "feed_id": feed["id"]})
    elif feed["id"] == "parliament-news":
        for href, label in parser.links:
            title = clean_text(label, 400)
            url = urllib.parse.urljoin(final_url, href)
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            is_article = (
                "/bg/news/" in parsed.path.casefold()
                or ({"id", "page"}.issubset(query.keys()) and query.get("page", [""])[0] in {"news", "show"})
                or "aid" in query
            )
            if len(title) < 35 or not is_article or not valid_url(url, feed["allowed_hosts"]):
                continue
            if title.casefold() in {"архив новини", "новини"}:
                continue
            rows.append({"section": feed["section"], "source": feed["name"], "title": title,
                         "summary": "", "url": url, "published": None, "feed_id": feed["id"]})
    else:
        for href, label in parser.links:
            title = clean_text(label, 400)
            url = urllib.parse.urljoin(final_url, href)
            if len(title) < 35 or not valid_url(url, feed["allowed_hosts"]):
                continue
            path = urllib.parse.urlparse(url).path.casefold()
            full_url = url.casefold()
            if feed["id"] == "parliament-news":
                if not (path.startswith("/bg/news/") or "aid=" in full_url or "newsid" in full_url):
                    continue
            elif not any(token in path or token in full_url for token in ("/news", "newsid", "news_id", "aid=")):
                continue
            if title.casefold() in {"архив новини", "новини"}:
                continue
            rows.append({"section": feed["section"], "source": feed["name"], "title": title,
                         "summary": "", "url": url, "published": None, "feed_id": feed["id"]})
    unique = {row["url"]: row for row in rows}
    if not unique:
        raise ValueError("No valid article links found on official HTML page")
    return list(unique.values())[:MAX_PER_FEED]

def fetch(feed):
    if feed["id"] == "parliament-news":
        return fetch_parliament_api(feed)
    if feed.get("mode") == "html":
        return fetch_html_news(feed)
    url = feed.get("url")
    if not url and feed.get("discovery_url"):
        discovery = feed["discovery_url"]
        if not valid_url(discovery, feed["allowed_hosts"]):
            raise ValueError("Discovery URL is not on the HTTPS host allowlist")
        req = urllib.request.Request(discovery, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            page_url = response.geturl()
            if not valid_url(page_url, feed["allowed_hosts"]):
                raise ValueError("Discovery redirected outside its host allowlist")
            page = response.read(MAX_BYTES + 1)
        if len(page) > MAX_BYTES:
            raise ValueError("Discovery page exceeds the 1 MB size limit")
        finder = LinkFinder()
        finder.feed(page.decode("utf-8", errors="replace"))
        matches = [(urllib.parse.urljoin(page_url, href), label) for href, label in finder.links
                   if href and (
                       feed["discovery_label"].casefold() in label.casefold()
                       or "rss" in href.casefold()
                       or "feed" in href.casefold()
                   )]
        candidates = []
        for candidate, _label in matches:
            if valid_url(candidate, feed["allowed_hosts"]) and candidate not in candidates:
                candidates.append(candidate)
        if not candidates:
            raise ValueError("No matching official RSS link found on discovery page")
        url = candidates[0]
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
    # Remove an external DOCTYPE before parsing; entity declarations stay forbidden.
    upper = raw.upper()
    if b"<!ENTITY" in upper:
        raise ValueError("XML entity declarations are not accepted")
    if b"<!DOCTYPE" in upper:
        start = upper.find(b"<!DOCTYPE")
        quote = None
        bracket_depth = 0
        end = None
        for pos in range(start + 9, len(raw)):
            ch = raw[pos]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in (34, 39):
                quote = ch
            elif ch == 91:
                bracket_depth += 1
            elif ch == 93:
                bracket_depth = max(0, bracket_depth - 1)
            elif ch == 62 and bracket_depth == 0:
                end = pos + 1
                break
        if end is None:
            raise ValueError("Malformed XML DOCTYPE declaration")
        raw = raw[:start] + raw[end:]
    root = ET.fromstring(raw)
    rows = []
    for node in root.iter():
        if local_name(node.tag) not in ("item", "entry"):
            continue
        title = clean_text(child_text(node, {"title"}), 400)
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
        # ECB's press RSS also contains speeches and interviews; keep formal releases.
        if feed["id"] == "ecb-press":
            path = urllib.parse.urlparse(link).path
            if "/press/pr/" not in path:
                continue
        rows.append({
            "section": feed["section"], "source": feed["name"],
            "title": title, "summary": description, "url": link,
            "published": date, "feed_id": feed["id"],
        })
        if len(rows) >= MAX_PER_FEED:
            break
    return rows

def classify_investor_section(item):
    """Move only clearly foreign-focused stories to Europe/world.

    Domestic relevance is determined first from the headline. The summary is
    deliberately excluded from the foreign-keyword test because Bulgarian
    stories often mention EU funds, Eurostat or international partners.
    """
    if item.get("feed_id") not in {"investor-economy", "investor-finance", "economic-bg"}:
        return item
    title = item.get("title", "").casefold()
    domestic_terms = (
        "българ", "софия", "столична община", "столичната община",
        "общин", "пловдив", "варна", "бургас", "русе", "стара загора",
        "перник", "въглищните регион", "българските домакинства",
        "монетният двор", "магистрал", "у нас", "в страната"
    )
    if any(term in title for term in domestic_terms):
        item["section"] = "bulgaria"
        return item
    international_terms = (
        "русия", "руски", "москва", "путин", "украйна", "украин", "киев",
        "съединените щати", "саш", "американ", "трамп", "китай", "пекин",
        "иран", "израел", "газа", "близкия изток", "нато", "wall street", "уолстрийт", "уол стрийт", "азия", "азиатск",
        "nvidia", "apple", "microsoft", "google", "amazon", "tesla",
        "deutsche bank", "lagarde", "лагард", "европейската комисия",
        "еврокомис", "европейския съюз", "еврозон", "европейската централна банка",
        "евростат", "ecb", "eurostat", "международния валутен фонд",
        "световния икономически форум", "световната банка", "герман",
        "франция", "френск", "британ", "великобритания", "италия", "испания",
        "полша", "унгария", "чехия", "сърбия", "турция", "япония", "индия",
        "корея", "саудитска арабия", "opec", "федералния резерв",
        "американската борса", "азиатските пазари", "европа", "европей", "евросъюз", "еврозон", "ецб", "фед", "федералн",
        "гърц", "гръц", "атин", "нискозем", "португал", "нидерланд", "австрия",
        "швейцар", "румън", "словак", "хърват", "литва", "латвия", "естония"
    )
    if any(term in title for term in international_terms):
        item["section"] = "europe"
    else:
        item["section"] = "bulgaria"
    return item


def _term_group_hits(text, groups):
    """Брой различни тематични групи, за да не се надценяват повтарящи се думи."""
    return sum(1 for group in groups if any(term in text for term in group))


ECONOMIC_GROUPS = (
    ("бюджет", "фискален дефицит", "държавен дълг", "публичен дълг", "budget", "public debt"),
    ("инфлац", "потребителски цени", "цени на храните", "inflation", "consumer prices"),
    ("бвп", "икономически растеж", "рецес", "производителност", "gdp", "economic growth", "recession", "productivity"),
    ("лихв", "парична политика", "централна банка", "банкова ликвидност", "interest rate", "monetary policy", "central bank"),
    ("кредит", "депозит", "банков", "ипотеч", "credit", "deposit", "banking", "mortgage"),
    ("данък", "данъц", "осигур", "приходи в бюджета", "tax", "social security"),
    ("инвестици", "капиталов разход", "индустриален парк", "investment", "capital expenditure"),
    ("износ", "внос", "търговски баланс", "мито", "export", "import", "trade balance", "tariff"),
    ("заплат", "доход", "пенси", "безработиц", "заетост", "работни места", "wage", "salary", "pension", "unemployment", "employment", "jobs"),
    ("енерги", "електроенерг", "природен газ", "петрол", "горив", "energy", "electricity", "natural gas", "oil", "fuel"),
    ("бизнес", "предприят", "пазар на труда", "бизнес климат", "company", "business", "labour market"),
)
NATIONAL_GROUPS = (
    ("българия", "български", "в страната", "за страната", "национал", "в цялата страна"),
    ("правителств", "министерств", "народното събрание", "парламент", "кабинет"),
    ("държавен бюджет", "държавна политика", "законопроект", "закон за", "национална стратегия"),
    ("нси", "бнб", "мф", "нои", "фискален съвет", "национален статистически"),
    ("всички общини", "общините в страната", "публичния сектор", "държавната администрация"),
)
HOUSEHOLD_BUSINESS_GROUPS = (
    ("цени", "инфлац", "покупателна способност", "price", "inflation", "purchasing power"),
    ("заплат", "доход", "пенси", "социални плащ", "wage", "income", "pension", "benefit"),
    ("данък", "осигур", "такс", "сметк", "tax", "social security", "fee", "bill"),
    ("лихв", "кредит", "ипотеч", "депозит", "interest", "loan", "mortgage", "deposit"),
    ("работни места", "заетост", "безработиц", "работодател", "employee", "employment", "job", "employer"),
    ("енерги", "ток", "газ", "горив", "транспорт", "electricity", "gas", "fuel", "transport"),
    ("малък бизнес", "предприят", "инвеститор", "производител", "small business", "enterprise", "investor", "manufacturer"),
    ("здравеопаз", "образован", "социално подпомаган", "обществена услуга", "healthcare", "education", "public service"),
)
STRATEGIC_GROUPS = (
    ("стратегическ", "национална сигурност", "отбран", "военн", "nato", "defence", "defense", "national security"),
    ("индустриален парк", "електромобил", "производствен капацитет", "чип", "изкуствен интелект", "industrial park", "electric vehicle", "semiconductor", "artificial intelligence"),
    ("чуждестранни инвестици", "стратегическа инвестици", "саудитска арабия", "foreign investment", "strategic investment"),
    ("енергийна сигурност", "ядрен", "електропренос", "газопровод", "energy security", "nuclear", "power grid", "pipeline"),
    ("инфраструктур", "железопът", "магистрал", "пристанищ", "коридор", "infrastructure", "railway", "highway", "port", "corridor"),
    ("европейски съюз", "еврозон", "европейска комисия", "санкци", "търговско споразумение", "european union", "eurozone", "european commission", "sanction", "trade agreement"),
    ("верига на достав", "критична суровина", "ключова технология", "supply chain", "critical raw material", "key technology"),
)
LOCALITY_TERMS = (
    "монтана", "благоевград", "русе", "пловдив", "варна", "бургас", "стара загора",
    "велико търново", "горна оряховица", "перник", "дупница", "сливен", "шумен",
    "добрич", "пазарджик", "хасково", "кърджали", "виден", "ямбол", "разград",
    "софия", "столичния", "столична община",
)
PUBLISHER_BY_FEED = {
    "investor-bg": "investor.bg",
    "investor-economy": "investor.bg",
    "investor-finance": "investor.bg",
    "bta-bulgaria": "БТА",
    "economic-bg": "Economic.bg",
    "parliament-news": "Народно събрание",
    "bnb-news": "БНБ",
    "ecb-press": "ЕЦБ",
    "commission-press": "Европейска комисия",
    "council-press": "Съвет на ЕС",
    "eurostat-news": "Евростат",
    "un-geneva-press": "ООН",
    "bbc-world": "BBC",
    "dw-world": "Deutsche Welle",
    "euronews": "Euronews",
    "guardian-world": "The Guardian",
    "politico-europe": "POLITICO",
    "federal-reserve": "Федерален резерв",
    "bis-press": "BIS",
    "bis-research": "BIS",
    "wto-news": "СТО",
}
SOURCE_RELIABILITY = {
    "parliament-news": 98,
    "bnb-news": 99,
    "ecb-press": 99,
    "commission-press": 99,
    "council-press": 99,
    "eurostat-news": 99,
    "federal-reserve": 99,
    "bis-press": 99,
    "bis-research": 99,
    "wto-news": 98,
    "un-geneva-press": 96,
    "bta-bulgaria": 90,
    "investor-bg": 87,
    "investor-economy": 87,
    "investor-finance": 87,
    "economic-bg": 85,
    "bbc-world": 95,
    "dw-world": 95,
    "euronews": 91,
    "guardian-world": 94,
    "politico-europe": 92,
}


def publisher_key(item):
    """Групира отделните RSS категории под един реален издател."""
    feed_id = str(item.get("feed_id") or "")
    if feed_id in PUBLISHER_BY_FEED:
        return PUBLISHER_BY_FEED[feed_id]
    source = re.sub(r"\s*[–-]\s*.*$", "", str(item.get("source") or "")).strip().casefold()
    return source or feed_id or "unknown"


def _recency_score(item, now=None):
    now = now or datetime.now(timezone.utc)
    published = publication_datetime(item)
    if published == datetime.min.replace(tzinfo=timezone.utc):
        return 0
    age_hours = max(0.0, (now - published).total_seconds() / 3600)
    if age_hours <= 3:
        return 100
    if age_hours <= 12:
        return 92
    if age_hours <= 24:
        return 82
    if age_hours <= 48:
        return 68
    if age_hours <= 96:
        return 50
    if age_hours <= 168:
        return 30
    return 10


def editorial_priority_components(item, now=None):
    """Оценява 6 отделни измерения; свежестта е само един от факторите."""
    now = now or datetime.now(timezone.utc)
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    text = (title + " " + summary).casefold()

    economic_hits = _term_group_hits(text, ECONOMIC_GROUPS)
    economic = min(100, economic_hits * 20 + (8 if economic_hits else 0))

    national_hits = _term_group_hits(text, NATIONAL_GROUPS)
    has_locality = any(term in text for term in LOCALITY_TERMS)
    if national_hits:
        national = min(100, 48 + national_hits * 13)
    elif has_locality:
        national = 22
    else:
        national = 34

    household_hits = _term_group_hits(text, HOUSEHOLD_BUSINESS_GROUPS)
    household_business = min(100, household_hits * 17 + (8 if household_hits else 0))

    strategic_hits = _term_group_hits(text, STRATEGIC_GROUPS)
    strategic = min(100, strategic_hits * 22 + (10 if strategic_hits else 0))

    recency = _recency_score(item, now)
    reliability = SOURCE_RELIABILITY.get(str(item.get("feed_id") or ""), 65)

    weights = {
        "economic_significance": 0.25,
        "national_impact": 0.24,
        "household_business_impact": 0.20,
        "strategic_significance": 0.16,
        "timeliness": 0.09,
        "source_reliability": 0.06,
    }
    dimensions = {
        "economic_significance": economic,
        "national_impact": national,
        "household_business_impact": household_business,
        "strategic_significance": strategic,
        "timeliness": recency,
        "source_reliability": reliability,
    }
    score = round(sum(dimensions[key] * weight for key, weight in weights.items()))
    return {**dimensions, "weights": weights, "score": max(0, min(100, score))}


def editorial_priority(item, now=None):
    """Композитна редакционна оценка от 0 до 100."""
    return editorial_priority_components(item, now)["score"]


def _event_type(item):
    text = (str(item.get("title") or "") + " " + str(item.get("summary") or "")).casefold()
    if any(term in text for term in ("стачк", "протест", "бойкот", "strike", "walkout")):
        return "labour_action"
    if any(term in text for term in ("повреда", "авари", "прекъсва", "спира движението", "outage", "disruption")):
        return "service_disruption"
    if any(term in text for term in ("инвестици", "открива завод", "нов завод", "investment", "factory")):
        return "investment"
    if any(term in text for term in ("бюджет", "дефицит", "държавен дълг", "budget", "fiscal")):
        return "public_finance"
    if any(term in text for term in ("лихвен процент", "парична политика", "interest rate", "monetary policy")):
        return "monetary_policy"
    return ""


EVENT_ACTOR_ANCHORS = (
    "подкрепа", "кнсб", "социално подпомагане", "регионална дирекция за социално подпомагане",
    "народно събрание", "европейска комисия", "европейска централна банка",
    "българска народна банка", "федерален резерв", "фискален съвет",
    "саудитска арабия", "лукойл", "булгаргаз", "енергийна система",
)


def _event_anchors(item):
    text = (str(item.get("title") or "") + " " + str(item.get("summary") or "")).casefold()
    return {anchor for anchor in EVENT_ACTOR_ANCHORS if anchor in text}


def _event_tokens(item):
    stop = {
        "това", "този", "тази", "тези", "които", "която", "което", "както", "заради",
        "след", "преди", "между", "около", "относно", "съобщи", "каза", "обяви", "според",
        "the", "and", "for", "from", "with", "that", "this", "have", "has", "will", "after",
        "нови", "нова", "ново", "днес", "утре", "вчера", "българия", "български",
    }
    text = (str(item.get("title") or "") + " " + str(item.get("summary") or "")).casefold()
    return {
        token for token in re.findall(r"[a-zа-яё]{3,}", text, flags=re.I)
        if token not in stop
    }


def _same_event(left, right, hours=48):
    left_date = publication_datetime(left)
    right_date = publication_datetime(right)
    if left_date == datetime.min.replace(tzinfo=timezone.utc) or right_date == datetime.min.replace(tzinfo=timezone.utc):
        return False
    if abs((left_date - right_date).total_seconds()) > hours * 3600:
        return False

    left_type, right_type = _event_type(left), _event_type(right)
    if not left_type or left_type != right_type:
        return False

    common_anchors = _event_anchors(left) & _event_anchors(right)
    if common_anchors:
        return True

    left_tokens = _event_tokens(left)
    right_tokens = _event_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = overlap / union if union else 0
    title_left = " ".join(re.findall(r"[a-zа-яё]{3,}", str(left.get("title") or "").casefold(), flags=re.I))
    title_right = " ".join(re.findall(r"[a-zа-яё]{3,}", str(right.get("title") or "").casefold(), flags=re.I))
    from difflib import SequenceMatcher
    title_similarity = SequenceMatcher(None, title_left, title_right).ratio()
    return jaccard >= 0.58 or title_similarity >= 0.76


def deduplicate_related_events(items):
    """Групира свързани отразявания на едно събитие, без да губи източниците."""
    ranked = sorted(items, key=lambda item: (
        float(item.get("priority_score", 0) or 0),
        publication_datetime(item),
    ), reverse=True)
    clusters = []
    for item in ranked:
        match = None
        for cluster in clusters:
            if any(_same_event(item, member) for member in cluster):
                match = cluster
                break
        if match is None:
            clusters.append([item])
        else:
            match.append(item)

    merged = []
    for cluster in clusters:
        representative = dict(cluster[0])
        related = list(representative.get("related_items") or [])
        for other in cluster[1:]:
            related.append({
                "source": other.get("source", ""),
                "publisher": other.get("publisher") or publisher_key(other),
                "title": other.get("title", ""),
                "url": other.get("url", ""),
                "published": other.get("published"),
            })
            related.extend(other.get("related_items") or [])
        unique_related = []
        seen_urls = {str(representative.get("url") or "")}
        for entry in related:
            url = str(entry.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_related.append(entry)
        if unique_related:
            representative["related_items"] = unique_related
            representative["related_count"] = len(unique_related)
        merged.append(representative)
    return merged


def is_recent_article(item, now=None):
    """Изключва записи без надеждна дата, прекалено стари записи и бъдещи дати."""
    now = now or datetime.now(timezone.utc)
    published = item.get("published")
    if not published:
        return False
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = now - dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return False
    if age < -timedelta(hours=FUTURE_DATE_TOLERANCE_HOURS):
        return False
    return age <= timedelta(days=MAX_ITEM_AGE_DAYS)



def publication_datetime(item):
    """Връща датата на публикация като UTC, независимо от записаната часова зона."""
    published = item.get("published")
    if not isinstance(published, str) or not published.strip():
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _rank_key(item):
    try:
        score = float(item.get("priority_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0
    return score, publication_datetime(item), str(item.get("title") or "").casefold()


def is_lead_eligible(item, now=None):
    """Връща True само за новина с надеждна дата в последните 18 часа."""
    now = now or datetime.now(timezone.utc)
    published = publication_datetime(item)
    if published == datetime.min.replace(tzinfo=timezone.utc):
        return False
    age_hours = (now - published).total_seconds() / 3600
    return -FUTURE_DATE_TOLERANCE_HOURS <= age_hours <= MAX_LEAD_AGE_HOURS


def select_news_items(items, limit=70, top_window=10, max_per_publisher=2, now=None):
    """Подрежда по значимост; водещата позиция се запазва за новина до 18 часа."""
    if limit <= 0:
        return []

    now = now or datetime.now(timezone.utc)
    sections = {}
    for item in items:
        sections.setdefault(item.get("section") or "other", []).append(item)

    protected = []
    remaining = []
    lead_by_section = {}
    for section, section_items in sections.items():
        ranked = sorted(section_items, key=_rank_key, reverse=True)
        lead = next((item for item in ranked if is_lead_eligible(item, now)), None)
        if lead is not None:
            lead_by_section[section] = lead
            ranked = [lead] + [item for item in ranked if item is not lead]

        top = []
        deferred = []
        publisher_counts = {}
        for item in ranked:
            publisher = item.get("publisher") or publisher_key(item)
            if len(top) < top_window and publisher_counts.get(publisher, 0) < max_per_publisher:
                top.append(item)
                publisher_counts[publisher] = publisher_counts.get(publisher, 0) + 1
            else:
                deferred.append(item)
        protected.extend(top)
        remaining.extend(deferred)

    ordered = sorted(protected, key=_rank_key, reverse=True)
    ordered.extend(sorted(remaining, key=_rank_key, reverse=True))
    selected = ordered[:limit]

    # Подреждаме най-значимата публикация от последните 18 часа първа във
    # всяка секция, без да променяме оценките и реда на останалите материали.
    for section, lead in lead_by_section.items():
        lead_index = next((i for i, item in enumerate(selected) if item is lead), None)
        if lead_index is None:
            continue
        first_section_index = next(
            (i for i, item in enumerate(selected) if (item.get("section") or "other") == section),
            None,
        )
        if first_section_index is not None and lead_index != first_section_index:
            selected.pop(lead_index)
            selected.insert(first_section_index, lead)

    return selected


def main():
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    all_items = []
    failures = []
    previous_items = previous.get("items", []) if isinstance(previous, dict) else []
    for feed in FEEDS:
        try:
            fresh = fetch(feed)
            all_items.extend(fresh)
        except Exception as exc:
            failures.append({"feed": feed["id"], "error": str(exc)[:180]})
            # Keep the last known-good entries for this feed if a temporary outage occurs.
            all_items.extend(x for x in previous_items if x.get("feed_id") == feed["id"])
    all_items = [classify_investor_section(item) for item in all_items]
    before_freshness = len(all_items)
    all_items = [item for item in all_items if is_recent_article(item)]
    print(f"Freshness gate: retained {len(all_items)}/{before_freshness} dated items within {MAX_ITEM_AGE_DAYS} days.")

    # Дедупликация по каноничен URL.
    dedup = {}
    for item in all_items:
        key = item["url"].split("#", 1)[0].rstrip("/")
        if key not in dedup or publication_datetime(item) > publication_datetime(dedup[key]):
            dedup[key] = item

    # Оценка по 6 измерения: икономика, национален обхват, домакинства/бизнес,
    # стратегическо значение, актуалност и надеждност на издателя.
    scored = []
    for item in dedup.values():
        item["publisher"] = publisher_key(item)
        components = editorial_priority_components(item)
        item["priority_score"] = components["score"]
        item["priority_breakdown"] = {
            key: value for key, value in components.items() if key not in {"weights", "score"}
        }
        scored.append(item)

    # Свързаните публикации се групират в една новина с допълнителни линкове.
    grouped = deduplicate_related_events(scored)

    # Първите 10 във всяка новинарска секция: максимум 2 материала от един издател.
    # След това останалите позиции се запълват по значимост и актуалност.
    items = select_news_items(grouped, limit=70, top_window=10, max_per_publisher=2)
    result = {
        "schema_version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
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
