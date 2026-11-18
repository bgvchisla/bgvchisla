#!/usr/bin/env python3
"""Import NSI monthly fiscal series from the official XLSX workbook."""
import io
import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from openpyxl import load_workbook

WORKBOOK_URL = "https://www.nsi.bg/sites/default/files/files/data/timeseries/GFS_monthly_fiscal_data_EUR_EN.xlsx"
SOURCE_PAGE = "https://www.nsi.bg/en/statistical-data/128/405"
OUTPUT = Path("official_fiscal.json")
MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}
TABLES = [
    {
        "start": 9, "sector": "central_government",
        "sector_title": "Централно управление",
    },
    {
        "start": 25, "sector": "social_security_funds",
        "sector_title": "Фондове за социална сигурност",
    },
]
METRICS = [
    ("balance", "Бюджетно салдо"),
    ("revenue", "Общо приходи"),
    ("expenditure", "Общо разходи"),
]

def download():
    req = urllib.request.Request(WORKBOOK_URL, headers={
        "User-Agent": "Mozilla/5.0 (compatible; bgvchisla-official-data/1.0; +https://bgvchisla.com)",
        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
    })
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read(20_000_001)
        if response.status != 200 or not raw.startswith(b"PK"):
            raise RuntimeError("НСИ не върна валиден XLSX файл")
    if len(raw) > 20_000_000:
        raise RuntimeError("Файлът на НСИ надхвърля лимита за безопасно изтегляне")
    return raw

def parse_workbook(raw):
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    if len(wb.worksheets) != 1:
        raise RuntimeError(f"Неочакван брой таблици: {len(wb.worksheets)}")
    ws = wb.worksheets[0]
    all_series = []
    latest_period = None
    for table in TABLES:
        year_row = 6 if table["start"] == 9 else 22
        month_row = 7 if table["start"] == 9 else 23
        points_by_metric = {key: [] for key, _ in METRICS}
        year = None
        for col in range(2, ws.max_column + 1):
            year_cell = ws.cell(year_row, col).value
            if isinstance(year_cell, int):
                year = year_cell
            month_name = ws.cell(month_row, col).value
            if not year or month_name not in MONTHS:
                continue
            month = MONTHS[month_name]
            period = f"{year:04d}-{month:02d}"
            values = []
            for offset, (metric, _) in enumerate(METRICS):
                value = ws.cell(table["start"] + offset, col).value
                if value is None:
                    values.append(None)
                    continue
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise RuntimeError(f"Невалидна стойност за {period}, {metric}")
                values.append(float(value))
                points_by_metric[metric].append({
                    "period": period, "year": year, "month": month,
                    "value": round(float(value), 6),
                })
            if all(v is not None for v in values):
                # Cross-check the source's accounting identity within 0.02 million EUR.
                if abs((values[1] - values[2]) - values[0]) > 0.02:
                    raise RuntimeError(f"Несъответствие приходи-разходи-салдо за {period} ({table['sector']})")
                latest_period = max(latest_period or period, period)
        for metric, title in METRICS:
            points = points_by_metric[metric]
            if len(points) < 100:
                raise RuntimeError(f"Недостатъчно наблюдения: {table['sector']} / {metric}: {len(points)}")
            if [p["period"] for p in points] != sorted(set(p["period"] for p in points)):
                raise RuntimeError(f"Дублирани или несортирани периоди: {table['sector']} / {metric}")
            all_series.append({
                "id": f"{table['sector']}_{metric}",
                "title": f"{title} — {table['sector_title']}",
                "sector": table["sector"],
                "metric": metric,
                "unit": "млн. евро",
                "frequency": "monthly",
                "points": points,
            })
    if len(all_series) != 6 or not latest_period:
        raise RuntimeError("Непълна структура на фискалните серии")
    # The workbook is expected to include the most recently released month (September 2026 at this run).
    if latest_period < "2026-08":
        raise RuntimeError(f"Последният период изглежда остарял: {latest_period}")
    return {
        "source": "Национален статистически институт (НСИ)",
        "source_url": SOURCE_PAGE,
        "workbook_url": WORKBOOK_URL,
        "methodology": "Месечни касови данни по ESA 2010; стойностите са без натрупване.",
        "unit": "млн. евро",
        "frequency": "monthly",
        "latest_period": latest_period,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "series": all_series,
    }

def main():
    fresh = parse_workbook(download())
    # Preserve the last good publication if source content unexpectedly regresses.
    if OUTPUT.exists():
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
        old_period = old.get("latest_period", "")
        if fresh["latest_period"] < old_period:
            raise RuntimeError(f"НСИ върна по-стар период ({fresh['latest_period']} < {old_period}); старите данни са запазени")
    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUTPUT)
    print(f"Validated {len(fresh['series'])} series, {sum(len(s['points']) for s in fresh['series'])} observations; latest={fresh['latest_period']}")
    for series in fresh["series"]:
        print(f"{series['id']}: {len(series['points'])} observations; latest value={series['points'][-1]['value']}")

if __name__ == "__main__":
    main()
