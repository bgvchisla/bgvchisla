#!/usr/bin/env python3
"""Inspect the official NSI monthly fiscal workbook without publishing values."""
import io
import urllib.error
import urllib.request
from openpyxl import load_workbook

FILENAME = "GFS_monthly_fiscal_data_EUR_EN.xlsx"
URLS = [
    f"https://www.nsi.bg/sites/default/files/files/data/timeseries/{FILENAME}",
    f"https://www.nsi.bg/en/statistical-data/128/sites/default/files/files/data/timeseries/{FILENAME}",
    f"https://new.nsi.bg/sites/default/files/files/data/timeseries/{FILENAME}",
]
headers = {
    "User-Agent": "Mozilla/5.0 (compatible; bgvchisla-data-inspector/1.0; +https://bgvchisla.com)",
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
}
raw = None
errors = []
for url in URLS:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            candidate = response.read(20_000_001)
            if response.status == 200 and candidate.startswith(b"PK"):
                raw = candidate
                print(f"Downloaded official NSI workbook from {url} (HTTP 200)")
                break
            errors.append(f"{url}: HTTP {response.status}, not an XLSX payload")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        errors.append(f"{url}: {exc}")
if raw is None:
    raise RuntimeError("Could not retrieve official NSI XLSX. " + " | ".join(errors))
if len(raw) > 20_000_000:
    raise RuntimeError("Workbook exceeds 20 MB safety limit")
wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
print("Workbook sheets:", wb.sheetnames)
for ws in wb.worksheets:
    print(f"\\nSHEET {ws.title!r} dimensions={ws.max_row}x{ws.max_column}")
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 24), values_only=True):
        values = [str(v)[:160] if v is not None else "" for v in row[:12]]
        if any(values):
            print(" | ".join(values))
