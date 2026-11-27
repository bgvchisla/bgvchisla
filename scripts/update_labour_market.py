#!/usr/bin/env python3
"""Refresh the current number of vacancies listed by Bulgaria's Employment Agency.

This importer updates only the live vacancy snapshot. Quarterly NSI survey
estimates and monthly administrative unemployment rates are not inferred from
the vacancy page and remain tied to their own official publications.
"""
from __future__ import annotations

import html
import json
import re
import ssl
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

URL = "https://az.government.bg/bg/ejobs/view_prl/"
OUTPUT = Path("labour-market.json")
UA = "Mozilla/5.0 (compatible; BgvchislaLabourMarket/1.0; +https://bgvchisla.com)"
MAX_BYTES = 8_000_000
TIMEOUT = 40


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str):
        self.parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", html.unescape(" ".join(self.parts))).strip()


def build_ssl_context() -> ssl.SSLContext:
    """Use certificate-verified TLS 1.2 with ECDHE-only ciphers for the AZ legacy host.

    The Employment Agency host currently negotiates undersized finite-field DH
    parameters with default clients. Do not lower OpenSSL's security level or
    disable certificate verification; instead, offer modern ECDHE suites only.
    """
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20")
    return context


def fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=build_ssl_context()) as response:
        if response.status != 200:
            raise RuntimeError(f"АЗ върна HTTP {response.status}")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise RuntimeError("Страницата на АЗ надвишава допустимия размер")
    return raw.decode("utf-8", errors="replace")


def parse_vacancy_snapshot(page_html: str) -> dict:
    parser = TextParser()
    parser.feed(page_html)
    text = parser.text
    pattern = (
        r"Към\s*(\d{2})/(\d{2})/(\d{4})\s+в\s+бюрата\s+по\s+труда\s+"
        r"има\s+заявени\s+([\d\s\u00a0]+?)\s+свободни\s+работни\s+места"
    )
    match = re.search(pattern, text, flags=re.I)
    if not match:
        raise RuntimeError("Не е открито ясно датирано число за свободните работни места на страницата на АЗ")
    day, month, year = (int(match.group(i)) for i in (1, 2, 3))
    try:
        date_value = datetime(year, month, day).date()
    except ValueError as exc:
        raise RuntimeError(f"Невалидна дата в страницата на АЗ: {exc}") from exc
    count_text = re.sub(r"\s+", "", match.group(4)).replace("\u00a0", "")
    if not count_text.isdigit():
        raise RuntimeError("Невалиден брой свободни работни места в страницата на АЗ")
    count = int(count_text)
    if count < 0 or count > 250_000:
        raise RuntimeError(f"Нереалистичен брой свободни работни места: {count}")
    return {
        "source": "Агенция по заетостта — електронна трудова борса",
        "source_url": URL,
        "as_of": date_value.isoformat(),
        "count": count,
        "definition": (
            "Текущ брой обяви за свободни работни места, заявени в бюрата по труда "
            "към датата на проверката. Това е моментна наличност в електронната борса, "
            "а не всички свободни работни места в икономиката."
        ),
    }


def main() -> None:
    if not OUTPUT.exists():
        raise RuntimeError("Липсва labour-market.json; отказ от създаване на непълен набор")
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    old = payload.get("active_vacancies", {})
    latest = parse_vacancy_snapshot(fetch(URL))

    old_date = old.get("as_of")
    if old_date and latest["as_of"] < old_date:
        raise RuntimeError(
            f"Регресия на датата на данните: новата дата {latest['as_of']} "
            f"е по-стара от публикуваната {old_date}"
        )
    if old_date == latest["as_of"] and old.get("count") == latest["count"]:
        print(f"Няма промяна в наличните свободни места към {latest['as_of']}: {latest['count']}.")
        return

    payload["active_vacancies"] = latest
    payload["last_updated"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUTPUT)
    print(
        f"Актуализирани свободни работни места: {latest['count']} "
        f"към {latest['as_of']}."
    )


if __name__ == "__main__":
    main()
