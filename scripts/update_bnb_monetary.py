#!/usr/bin/env python3
"""Import verified monthly household credit series from the official BNB workbook."""
import io, json, math, urllib.request
from datetime import datetime, date
from pathlib import Path
from openpyxl import load_workbook

URL = "https://www.bnb.bg/bnbweb/groups/public/documents/bnb_download/s_monetarystatistics_all_bg.xlsx"
SOURCE = "https://www.bnb.bg/Statistics/StMonetaryInterestRate/StMonetaryStatistics/index.htm"
OUT = Path("official_bnb.json")
SHEET = "Cred_BG"
# Verified household loan categories; source values are thousand EUR.
SERIES = {
    "household_consumer_loans": (32, "Потребителски кредити", "Потребителски кредити на домакинствата и НТООД"),
    "household_housing_loans": (50, "Жилищни кредити", "Жилищни кредити на домакинствата и НТООД"),
    "household_other_loans": (68, "Други кредити", "Други кредити на домакинствата и НТООД"),
}

def iso_month(v):
    if isinstance(v, (datetime, date)): return v.strftime("%Y-%m")
    raise ValueError(f"Unexpected date cell: {v!r}")

def main():
    req = urllib.request.Request(URL, headers={"User-Agent":"Mozilla/5.0 (compatible; Bgvchisla/1.0)"})
    with urllib.request.urlopen(req, timeout=90) as response: raw = response.read(50_000_001)
    if len(raw) > 50_000_000 or not raw.startswith(b"PK"): raise ValueError("BNB workbook download is not a valid XLSX")
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    if SHEET not in wb.sheetnames: raise ValueError(f"Missing sheet {SHEET}")
    ws = wb[SHEET]
    periods = [(col, iso_month(ws.cell(2, col).value)) for col in range(2, ws.max_column + 1) if ws.cell(2, col).value is not None]
    if len(periods) < 100: raise ValueError(f"Too few monthly periods: {len(periods)}")
    for row, expected, _label in SERIES.values():
        actual = str(ws.cell(row, 1).value or "").strip()
        if actual != expected: raise ValueError(f"Source row mapping changed at {row}: {actual!r} != {expected!r}")
    if periods != sorted(periods, key=lambda x:x[1]) or len({p for _,p in periods}) != len(periods):
        raise ValueError("Periods are not strictly ordered and unique")
    result = {}
    for key, (row, expected, label) in SERIES.items():
        points = []
        for col, period in periods:
            value = ws.cell(row, col).value
            if value is None: continue
            value = float(value) / 1000.0
            if not math.isfinite(value) or value < 0: raise ValueError(f"Invalid value {key} {period}: {value}")
            points.append({"period":period,"value":round(value,3)})
        if len(points) < 100 or points[-1]["period"] != periods[-1][1]: raise ValueError(f"Incomplete series {key}")
        result[key] = {"label":label,"unit":"млн. евро","frequency":"месечна","points":points}
    latest = periods[-1][1]
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    if previous and latest < previous.get("latest_period",""): raise ValueError("BNB data regression: refusing to replace newer published data")
    payload = {
        "source":"Българска народна банка","source_url":SOURCE,"workbook_url":URL,
        "dataset":"Потребителски, жилищни и други кредити на домакинствата и НТООД, резиденти на България",
        "methodology":"Месечни салда към края на отчетния период. Оригиналните стойности в хил. евро са преобразувани в млн. евро (деление на 1000). Показани са три отделни категории кредити на домакинствата; те не представляват общия кредитен портфейл.",
        "unit":"млн. евро","frequency":"месечна","latest_period":latest,
        "updated_at":datetime.utcnow().replace(microsecond=0).isoformat()+"Z","series":result
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"BNB import OK: {len(result)} verified household series, {len(periods)} months, latest={latest}")
    for key, item in result.items(): print(key, item["points"][-1])

if __name__ == "__main__": main()
