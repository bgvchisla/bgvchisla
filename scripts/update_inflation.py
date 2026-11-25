#!/usr/bin/env python3
"""Refresh monthly consumer-price data from the latest final NSI release.

The importer is deliberately fail-closed: it writes inflation.json only after
validating the release period, CPI/HICP metrics, the CPI category table and the
continuity of the historical series. A failed fetch or schema change leaves the
last published dataset untouched.
"""
from __future__ import annotations

import html
import json
import math
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

INDEX_URL = "https://www.nsi.bg/press-release"
OUTPUT = Path("inflation.json")
UA = "Mozilla/5.0 (compatible; BgvchislaInflationData/1.0; +https://bgvchisla.com)"
MAX_BYTES = 8_000_000
TIMEOUT = 45

MONTHS = {
    "януари": 1, "февруари": 2, "март": 3, "април": 4,
    "май": 5, "юни": 6, "юли": 7, "август": 8,
    "септември": 9, "октомври": 10, "ноември": 11, "декември": 12,
}
MONTH_LABELS = {
    1: "Яну", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Юни",
    7: "Юли", 8: "Авг", 9: "Сеп", 10: "Окт", 11: "Ное", 12: "Дек",
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href is not None:
            self.items.append((self.current_href, " ".join(self.current_text)))
            self.current_href = None
            self.current_text = []


class ReportParser(HTMLParser):
    """Extract normalized page text and HTML tables without third-party libraries."""
    BLOCKS = {"p", "div", "h1", "h2", "h3", "h4", "li", "br", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.ignore_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag in self.BLOCKS:
            self.parts.append(" ")
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.ignore_depth:
            return
        self.parts.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self.ignore_depth:
            self.ignore_depth -= 1
            return
        if self.ignore_depth:
            return
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            value = normalize(" ".join(self.cell))
            self.row.append(value)
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None

    @property
    def text(self):
        return normalize(" ".join(self.parts))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES + 1)
        if response.status != 200:
            raise RuntimeError(f"НСИ върна HTTP {response.status} за {url}")
    if len(raw) > MAX_BYTES:
        raise RuntimeError(f"Официалният отговор надхвърля лимита от {MAX_BYTES} байта")
    return raw


def absolute_url(href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://www.nsi.bg" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    raise ValueError(f"Неподдържан адрес от НСИ: {href!r}")


def report_period(label: str) -> str | None:
    match = re.search(
        r"\b(януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември)\s+(20\d{2})\b",
        normalize(label).lower(),
    )
    if not match:
        return None
    return f"{int(match.group(2)):04d}-{MONTHS[match.group(1)]:02d}"


def discover_latest_release(index_html: str) -> tuple[str, str, str]:
    parser = LinkParser()
    parser.feed(index_html)
    candidates = []
    seen = set()
    for href, label in parser.items:
        normalized = normalize(label)
        lowered = normalized.lower()
        if "инфлация и индекси на потребителските цени" not in lowered:
            continue
        if any(term in lowered for term in ("експресна предварителна оценка", "предварителни данни", "предварителна оценка")):
            continue
        period = report_period(normalized)
        if not period or href in seen:
            continue
        seen.add(href)
        candidates.append((period, absolute_url(href), normalized))
    if not candidates:
        raise RuntimeError("В индекса на НСИ не е открита окончателна публикация за потребителските цени")
    candidates.sort(key=lambda row: row[0])
    return candidates[-1]


def parse_number(match_value: str) -> float:
    value = normalize(match_value).lower().replace(",", ".").replace("−", "-")
    negative_word = value.startswith("минус ")
    if negative_word:
        value = value[6:].strip()
    number = float(value)
    if negative_word:
        number = -abs(number)
    if not math.isfinite(number) or abs(number) > 1000:
        raise ValueError(f"Невалиден процент в публикацията: {match_value!r}")
    return round(number, 4)


def find_percent(pattern: str, text: str, label: str, required: bool = True):
    match = re.search(pattern, text, flags=re.I)
    if not match:
        if required:
            raise RuntimeError(f"Не е открит показателят „{label}“ в публикацията на НСИ")
        return None
    return parse_number(match.group(1))


def extract_metric_block(block: str, label: str) -> dict:
    monthly = find_percent(
        r"месечната инфлация\s*(?:,\s*измерена с [^,]{1,50},)?\s*е\s*(минус\s+)?([−\-]?\d+(?:[.,]\d+)?)\s*%",
        block, label + " месечна"
    )
    # The regular expression above has an optional word group; normalize the two capture groups.
    m = re.search(
        r"месечната инфлация\s*(?:,\s*измерена с [^,]{1,50},)?\s*е\s*(минус\s+)?([−\-]?\d+(?:[.,]\d+)?)\s*%",
        block, flags=re.I
    )
    if not m:
        raise RuntimeError(f"Не е открита месечната инфлация по {label}")
    monthly_value = parse_number(("минус " if m.group(1) else "") + m.group(2))

    a = re.search(
        r"годишната инфлация(?:\s+за[^%]{0,180})?\s+е\s*(минус\s+)?([−\-]?\d+(?:[.,]\d+)?)\s*%",
        block, flags=re.I
    )
    if not a:
        raise RuntimeError(f"Не е открита годишната инфлация по {label}")
    annual_value = parse_number(("минус " if a.group(1) else "") + a.group(2))

    ytd = find_percent(
        r"инфлацията от началото на годината[^%]{0,220}?\s+е\s*(?:минус\s+)?([−\-]?\d+(?:[.,]\d+)?)\s*%",
        block, label + " от началото на годината", required=False
    )
    annual_average = find_percent(
        r"средногодишната инфлация[^%]{0,240}?\s+е\s*(?:минус\s+)?([−\-]?\d+(?:[.,]\d+)?)\s*%",
        block, label + " средногодишна", required=False
    )
    return {
        "monthly": monthly_value,
        "annual": annual_value,
        "ytd": ytd,
        "annual_average": annual_average,
    }


def extract_accumulated(text: str, indicator: str) -> tuple[float | None, float | None]:
    match = re.search(
        r"натрупаната инфлация[^.]{0,100}" + re.escape(indicator) +
        r"[^.]{0,220}?последните три години[^%]{0,140}?\s+е\s*([−\-]?\d+(?:[.,]\d+)?)\s*%[^.]{0,220}?последните пет години[^%]{0,140}?\s+е\s*([−\-]?\d+(?:[.,]\d+)?)\s*%",
        text, flags=re.I
    )
    if not match:
        return None, None
    return parse_number(match.group(1)), parse_number(match.group(2))


def parse_small_basket(text: str) -> dict | None:
    match = re.search(
        r"месечното изменение на индекса на цените на малката кошница[^%]{0,180}?\s+е\s*([−\-]?\d+(?:[.,]\d+)?)\s*%[^.]{0,220}?годишното изменение[^%]{0,180}?\s+е\s*([−\-]?\d+(?:[.,]\d+)?)\s*%",
        text, flags=re.I
    )
    if not match:
        return None
    return {"monthly": parse_number(match.group(1)), "annual": parse_number(match.group(2))}


def parse_index_cell(value: str) -> float:
    number = float(normalize(value).replace(",", ".").replace(" ", ""))
    if not math.isfinite(number) or number < 0 or number > 1000:
        raise ValueError(f"Невалиден индекс в таблицата на НСИ: {value!r}")
    return round(number - 100.0, 4)


def extract_cpi_categories(tables: list[list[list[str]]]) -> list[dict]:
    for table in tables:
        rows = []
        for row in table:
            if len(row) < 5:
                continue
            code = normalize(row[0])
            if not re.fullmatch(r"\d{2}", code):
                continue
            try:
                values = [parse_index_cell(v) for v in row[-3:]]
            except (ValueError, TypeError):
                continue
            if code == "00":
                continue
            rows.append({
                "code": code,
                "category": normalize(row[1]),
                "monthly_change": values[0],
                "ytd_change": values[1],
                "annual_change": values[2],
            })
        if len(rows) >= 10:
            return rows
    raise RuntimeError("Не е открита пълната таблица с потребителски групи на ИПЦ в публикацията на НСИ")


def parse_release(period: str, source_url: str, label: str, page_html: str, old: dict) -> dict:
    parser = ReportParser()
    parser.feed(page_html)
    text = parser.text
    cpi_heading = re.search(r"индекс на потребителските цени\s*\(ипц\)", text, flags=re.I)
    hicp_heading = re.search(r"хармонизиран индекс на потребителските цени\s*\(хипц\)", text, flags=re.I)
    if not cpi_heading or not hicp_heading or hicp_heading.start() <= cpi_heading.end():
        raise RuntimeError("Неочаквана структура на публикацията на НСИ: липсват секциите ИПЦ/ХИПЦ")
    small_heading = re.search(r"индекс на цените[^.]{0,70}малката кошница|индекс на малката кошница", text, flags=re.I)
    cpi_block = text[cpi_heading.end():hicp_heading.start()]
    hicp_end = small_heading.start() if small_heading and small_heading.start() > hicp_heading.end() else len(text)
    hicp_block = text[hicp_heading.end():hicp_end]
    cpi = extract_metric_block(cpi_block, "ИПЦ")
    hicp = extract_metric_block(hicp_block, "ХИПЦ")

    cpi_3y, cpi_5y = extract_accumulated(cpi_block, "измерена с ИПЦ")
    hicp_3y, hicp_5y = extract_accumulated(hicp_block, "измерена с ХИПЦ")
    if cpi_3y is None or cpi_5y is None:
        cpi_3y, cpi_5y = extract_accumulated(text, "измерена с ИПЦ")
    if hicp_3y is None or hicp_5y is None:
        hicp_3y, hicp_5y = extract_accumulated(text, "измерена с ХИПЦ")

    categories = extract_cpi_categories(parser.tables)
    if cpi["ytd"] is None:
        raise RuntimeError("Липсва натрупаната инфлация от началото на годината по ИПЦ")
    if hicp["ytd"] is None:
        raise RuntimeError("Липсва натрупаната инфлация от началото на годината по ХИПЦ")

    month_num = int(period.split("-")[1])
    month_label = MONTH_LABELS[month_num]
    point = {
        "period": period,
        "label": month_label,
        "cpi_monthly": cpi["monthly"],
        "cpi_yoy": cpi["annual"],
        "hicp_monthly": hicp["monthly"],
        "hicp_yoy": hicp["annual"],
        "source_url": source_url,
    }
    history = list(old.get("history", []))
    by_period = {row.get("period"): row for row in history}
    by_period[period] = point
    history = [by_period[key] for key in sorted(by_period) if key]

    previous_period = old.get("latest_period")
    if previous_period and period < previous_period:
        raise RuntimeError(f"НСИ е открил по-стар период ({period}) спрямо публикувания ({previous_period}); отказ от регресия")
    if len(history) > 1 and [r["period"] for r in history] != sorted(set(r["period"] for r in history)):
        raise RuntimeError("Историческата серия съдържа дублирани или несортирани периоди")
    for row in history:
        for key in ("cpi_monthly", "cpi_yoy", "hicp_monthly", "hicp_yoy"):
            if not isinstance(row.get(key), (int, float)) or not math.isfinite(row[key]):
                raise RuntimeError(f"Невалидно наблюдение {row.get('period')} / {key}")

    payload = dict(old)
    payload.update({
        "source": "Национален статистически институт (НСИ)",
        "source_url": source_url,
        "latest_period": period,
        "latest_label": f"{MONTHS_BG(period)}",
        "latest_status": "Окончателни данни на НСИ",
        "history": history,
        "cpi_categories": categories,
        "latest": {
            "cpi": {
                **cpi,
                "accumulated_3y": cpi_3y,
                "accumulated_5y": cpi_5y,
            },
            "hicp": {
                **hicp,
                "accumulated_3y": hicp_3y,
                "accumulated_5y": hicp_5y,
            },
            "small_basket": parse_small_basket(text) or old.get("latest", {}).get("small_basket"),
        },
        "last_updated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })
    if payload["latest"]["small_basket"] is None:
        raise RuntimeError("Липсват данни за индекса на малката кошница; запазва се последният валиден набор")
    if payload["latest"]["cpi"]["accumulated_3y"] is None or payload["latest"]["hicp"]["accumulated_3y"] is None:
        raise RuntimeError("Липсват натрупаните показатели за 3 и 5 години")
    if not payload.get("source_history"):
        payload["source_history"] = []
    source_history = {r["period"]: r for r in payload["source_history"] if r.get("period")}
    source_history[period] = {"period": period, "url": source_url}
    payload["source_history"] = [source_history[key] for key in sorted(source_history)]
    return payload


def MONTHS_BG(period: str) -> str:
    month = int(period.split("-")[1])
    return f"{MONTHS[month] if isinstance(month, int) else ''} {period[:4]} г."


def main():
    if not OUTPUT.exists():
        raise RuntimeError("Липсва inflation.json; първоначалният проверен набор трябва да бъде създаден преди импорта")
    old = json.loads(OUTPUT.read_text(encoding="utf-8"))
    index_html = fetch(INDEX_URL).decode("utf-8", errors="replace")
    period, source_url, label = discover_latest_release(index_html)
    report_html = fetch(source_url).decode("utf-8", errors="replace")
    fresh = parse_release(period, source_url, label, report_html, old)

    old_latest = old.get("latest", {})
    if period == old.get("latest_period") and fresh.get("latest") == old_latest and fresh.get("cpi_categories") == old.get("cpi_categories"):
        print(f"Няма промяна в окончателните данни на НСИ за {period}; последният валиден набор се запазва.")
        return

    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUTPUT)
    print(f"Обновени официални данни от НСИ: {period}; наблюдения в серията: {len(fresh['history'])}; потребителски групи: {len(fresh['cpi_categories'])}")


if __name__ == "__main__":
    main()
