#!/usr/bin/env python3
"""Check reachability and publication-page metadata for official Bulgarian data sources.

This is a source-health monitor, not a statistical data importer. It deliberately
does not change indicator values. Numeric integrations are added only after each
source's downloadable/API schema has been verified.
"""
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

OUT = Path("source_status.json")
TIMEOUT = 30
MAX_BYTES = 4_000_000
UA = "bgvchisla-official-source-monitor/1.1 (+https://bgvchisla.com)"

SOURCES = [
    {
        "id": "minfin_budget",
        "name": "Министерство на финансите — месечно изпълнение на бюджета",
        "url": "https://www.minfin.bg/bg/statistics/18",
        "frequency": "месечно",
        "expected_terms": [["държавния бюджет", "държавен бюджет"], ["месеч"]],
        "expected": "Данни по държавния бюджет и месечни таблици за изпълнението",
        "owner": "Министерство на финансите",
    },
    {
        "id": "bnb_monetary_statistics",
        "name": "Българска народна банка — парична статистика",
        "url": "https://www.bnb.bg/Statistics/StMonetaryInterestRate/StMonetaryStatistics/index.htm",
        "frequency": "месечно",
        "expected_terms": [["парична статистика", "паричната статистика"], ["кредит", "депозит"]],
        "expected": "Парична статистика с таблици за кредити и депозити",
        "owner": "Българска народна банка",
    },
    {
        "id": "bnb_deposits_loans",
        "name": "Българска народна банка — кредити и депозити",
        "url": "https://www.bnb.bg/Statistics/StMonetaryInterestRate/StDepositsAndLoans/StDCDeposits/StDCDepositsQuarterlyData/index.htm",
        "frequency": "тримесечно",
        "expected_terms": [["кредит", "кредити"], ["депозит", "депозити"]],
        "expected": "Статистика и таблици за кредити и депозити",
        "owner": "Българска народна банка",
    },
    {
        "id": "bnb_interest_rates",
        "name": "Българска народна банка — лихвена статистика",
        "url": "https://www.bnb.bg/Statistics/StMonetaryInterestRate/StInterestRate/StIRInterestRate/",
        "frequency": "месечно",
        "expected_terms": [["лихвен", "лихвена", "лихвени"], ["статистика", "таблици"]],
        "expected": "Лихвена статистика и таблици с лихвени проценти",
        "owner": "Българска народна банка",
    },
    {
        "id": "nsi_sdmx",
        "name": "НСИ — SDMX база за разпространение",
        "url": "https://www.nsi.bg/ddb2.1/?l=bg",
        "frequency": "според показателя",
        "expected_terms": [["sdmx"], ["данни"], ["dsd", "структур"]],
        "expected": "SDMX 2.1 файлове за данни и DSD структури",
        "owner": "Национален статистически институт",
    },
    {
        "id": "nsi_statistical_data",
        "name": "НСИ — статистически данни за бедност и социално включване",
        "url": "https://www.nsi.bg/statistical-data/146",
        "frequency": "годишно",
        "expected_terms": [["бедност", "бедността"], ["доходи", "доход"]],
        "expected": "Доходи, бедност и социални показатели",
        "owner": "Национален статистически институт",
    },
    {
        "id": "nssi_pensions",
        "name": "НОИ — статистика на пенсиите",
        "url": "https://www.nssi.bg/publikacii/statistika/pensii-statistika/",
        "frequency": "тримесечно/годишно",
        "expected_terms": [["пенси"], ["статистик", "бюлетин", "годишник"]],
        "expected": "Статистика, бюлетини и годишници за пенсии и пенсионери",
        "owner": "Национален осигурителен институт",
    },
]

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.text_parts = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.links.append(href)
    def handle_data(self, data):
        if data.strip():
            self.text_parts.append(data)

def downloadable_link(href):
    path = urlsplit(href).path.lower()
    if re.search(r"\.(xlsx?|csv|pdf)$", path):
        return True
    # NSI SDMX exposes data/DSD files through these named PHP endpoints.
    return path.rsplit("/", 1)[-1] in {"download_data.php", "download_dsd.php"}

def check(source):
    req = urllib.request.Request(source["url"], headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            final_url = response.geturl()
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise RuntimeError("Страницата надвишава лимита за проверка от 4 MB")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        if "html" not in content_type.lower():
            raise RuntimeError(f"Неочакван Content-Type: {content_type[:120]}")
        text = body.decode("utf-8", errors="replace")
        parser = PageParser()
        parser.feed(text)
        page_text = " ".join(parser.text_parts).casefold()
        groups = source["expected_terms"]
        missing = [terms for terms in groups if not any(term.casefold() in page_text for term in terms)]
        files = {
            urljoin(final_url, href)
            for href in parser.links
            if downloadable_link(urljoin(final_url, href))
        }
        content_ok = not missing
        result = {
            "id": source["id"],
            "name": source["name"],
            "owner": source["owner"],
            "url": source["url"],
            "frequency": source["frequency"],
            "expected": source["expected"],
            "status": "ok" if content_ok else "content_mismatch",
            "http_status": status,
            "content_type": content_type[:120],
            "final_url": final_url,
            "download_links_detected": len(files),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "response_seconds": round(time.monotonic() - started, 2),
            "note": (
                "HTTP достъпността и очакваните тематични термини са проверени; това не потвърждава актуалността на всяка статистическа серия."
                if content_ok else
                "Страницата отговаря, но липсват очаквани тематични термини: " + "; ".join(", ".join(group) for group in missing)
            ),
        }
        return result
    except Exception as exc:
        restricted = isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 429)
        return {
            "id": source["id"],
            "name": source["name"],
            "owner": source["owner"],
            "url": source["url"],
            "frequency": source["frequency"],
            "expected": source["expected"],
            "status": "restricted" if restricted else "error",
            "error": str(exc)[:240],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": ("Автоматизираната среда е ограничена от сървъра на източника; това не означава, че официалната страница е недостъпна за посетители." if restricted else "Източникът не премина проверката за достъпност и съдържание."),
        }

def main():
    results = [check(source) for source in SOURCES]
    result = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": "source_availability_and_page_topic",
        "ok": sum(row["status"] == "ok" for row in results),
        "total": len(results),
        "sources": results,
        "notice": "Статусът показва HTTP достъпност и съответствие на страницата с очакваната тема; не удостоверява актуалността на последното статистическо наблюдение.",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Official source checks: {result['ok']}/{result['total']} passed")
    for row in results:
        print(row["status"].upper(), row["id"], row.get("http_status", row.get("error", "")), row.get("download_links_detected", ""))

if __name__ == "__main__":
    main()
