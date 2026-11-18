#!/usr/bin/env python3
"""Read-only inspection of official BNB monetary-statistics workbook."""
import io
import urllib.request
from openpyxl import load_workbook

URL = "https://www.bnb.bg/bnbweb/groups/public/documents/bnb_download/s_monetarystatistics_all_bg.xlsx"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 bgvchisla official data probe"})
with urllib.request.urlopen(req, timeout=60) as response:
    raw = response.read(50_000_001)
    print("HTTP", response.status, "content-type", response.headers.get("Content-Type"), "bytes", len(raw))
if len(raw) > 50_000_000 or not raw.startswith(b"PK"):
    raise SystemExit("Invalid or oversized XLSX")
wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
print("SHEETS", len(wb.sheetnames), wb.sheetnames)
for ws in wb.worksheets:
    print("\nSHEET", repr(ws.title), "rows", ws.max_row, "cols", ws.max_column)
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12), values_only=True):
        vals = [v for v in row[:12]]
        print("ROW", repr(vals))
