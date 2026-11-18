#!/usr/bin/env python3
"""Inspect the official NSI monthly fiscal workbook without publishing values."""
import io
import urllib.request
from openpyxl import load_workbook

URL = "https://www.nsi.bg/en/statistical-data/128/sites/default/files/files/data/timeseries/GFS_monthly_fiscal_data_EUR_EN.xlsx"
req = urllib.request.Request(URL, headers={
    "User-Agent": "bgvchisla-data-inspector/1.0 (+https://bgvchisla.com)",
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
})
with urllib.request.urlopen(req, timeout=60) as response:
    if response.status != 200:
        raise RuntimeError(f"NSI workbook HTTP {response.status}")
    raw = response.read(20_000_001)
if len(raw) > 20_000_000:
    raise RuntimeError("Workbook exceeds 20 MB safety limit")
if not raw.startswith(b"PK"):
    raise RuntimeError("NSI response is not an XLSX file")
wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
print("Workbook sheets:", wb.sheetnames)
for ws in wb.worksheets:
    print(f"\nSHEET {ws.title!r} dimensions={ws.max_row}x{ws.max_column}")
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 24), values_only=True):
        values = [str(v)[:160] if v is not None else "" for v in row[:12]]
        if any(values):
            print(" | ".join(values))
