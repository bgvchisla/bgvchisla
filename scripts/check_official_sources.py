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

OUT = Path("source_status.json")
TIMEOUT = 30
MAX_BYTES = 4_000_000
UA = "bgvchisla-official-source-monitor/1.0 (+https://bgvchisla.com)"

SOURCES = [
    {
        "id": "minfin_budget",
        "name": "Министерство на финансите — месечно изпълнение на бюджета",
        "url": "https://www.minfin.bg/bg/statistics/5",
        "frequency": "месечно",
        "expected": "Месечни таблици за изпълнението на държавния бюджет",
        "owner": "Министерство на финансите",
    },
    {
        "id": "bnb_statistics",
        "name": "Българска народна банка — парична и лихвена статистика",
        "url": "https://www.bnb.bg/Statistics/StStatisticalBD/",
        "frequency": "месечно/тримесечно",
        "expected": "Кредити, депозити и лихвени проценти",
        "owner": "Българска народна банка",
    },
    {
        "id": "nsi_sdmx",
        "name": "НСИ — SDMX база за разпространение",
        "url": "https://www.nsi.bg/ddb2.1/?l=bg",
        "frequency": "според показателя",
        "expected": "Официални статистически набори и SDMX структури",
        "owner": "Национален статистически институт",
    },
    {
        "id": "nsi_statistical_data",
        "name": "НСИ — статистически данни за бедност и социално включване",
        "url": "https://www.nsi.bg/statistical-data/146",
        "frequency": "годишно",
        "expected": "Доходи, бедност и социални показатели",
        "owner": "Национален статистически институт",
    },
    {
        "id": "nssi_pensions",
        "name": "НОИ — статистика на пенсиите",
        "url": "https://www.nssi.bg/publikacii/statistika/pensii-statistika/",
        "frequency": "тримесечно/годишно",
        "expected": "Бюлетини и годишници за пенсии и пенсионери",
        "owner": "Национален осигурителен институт",
    },
]

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            a = dict(attrs)
            href = a.get("href", "")
            if href:
                self.items.append(href)

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
        text = body.decode("utf-8", errors="replace")
        parser = Links()
        parser.feed(text)
        # Count downloadable statistical files without downloading them.
        files = [
            href for href in parser.items
            if re.search(r"\.(xlsx?|csv|pdf)(?:$|[?#])", href, re.I)
        ]
        return {
            "id": source["id"],
            "name": source["name"],
            "owner": source["owner"],
            "url": source["url"],
            "frequency": source["frequency"],
            "expected": source["expected"],
            "status": "ok",
            "http_status": status,
            "content_type": content_type[:120],
            "final_url": final_url,
            "download_links_detected": len(files),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "response_seconds": round(time.monotonic() - started, 2),
            "note": "Проверена достъпността на официалната страница; това не потвърждава актуалността на всяка статистическа серия.",
        }
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
            "note": ("Автоматизираната среда е ограничена от сървъра на източника; това не означава, че официалната страница е недостъпна за посетители." if restricted else "Източникът не премина проверката за достъпност."),
        }

def main():
    results = [check(source) for source in SOURCES]
    result = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": "source_availability_only",
        "ok": sum(row["status"] == "ok" for row in results),
        "total": len(results),
        "sources": results,
        "notice": "Статусът показва достъпност на официалните страници, а не дата на последното статистическо наблюдение.",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Official source availability: {result['ok']}/{result['total']} reachable")
    for row in results:
        print(row["status"].upper(), row["id"], row.get("http_status", row.get("error", "")))

if __name__ == "__main__":
    main()
