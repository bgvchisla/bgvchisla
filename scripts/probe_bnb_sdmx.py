#!/usr/bin/env python3
"""Compact inspection of key rows in the official BNB workbook."""
import io, urllib.request
from openpyxl import load_workbook
URL="https://www.bnb.bg/bnbweb/groups/public/documents/bnb_download/s_monetarystatistics_all_bg.xlsx"
req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 bgvchisla official data probe"})
with urllib.request.urlopen(req,timeout=60) as r:
    raw=r.read(50_000_001)
if len(raw)>50_000_000 or not raw.startswith(b"PK"): raise SystemExit("Invalid XLSX")
wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
for name in ["Cred_BG","aggregates","BNB Dynamic"]:
    ws=wb[name]
    print("\n###",name,"rows",ws.max_row,"cols",ws.max_column)
    date_row=2 if name in ["Cred_BG","BNB Dynamic"] else None
    if date_row:
        dates=[ws.cell(date_row,c).value for c in range(2,ws.max_column+1)]
        valid=[(c,v) for c,v in zip(range(2,ws.max_column+1),dates) if v is not None]
        print("DATE RANGE",valid[0] if valid else None,valid[-1] if valid else None)
        last_col=valid[-1][0] if valid else ws.max_column
    else:
        last_col=ws.max_column
    for i in range(1,ws.max_row+1):
        label=ws.cell(i,1).value
        if not isinstance(label,str): continue
        text=label.strip().upper()
        if any(k in text for k in ["НЕФИНАНСОВИ ПРЕДПРИЯТИЯ","ДОМАКИНСТВА","ОБЩО","РЕДОВНИ","КРЕДИТИ","ДЕПОЗИТИ","M1","M2","M3","ПАРИ В ОБРАЩЕНИЕ"]):
            print("ROW",i,repr(label),"LATEST",repr(ws.cell(i,last_col).value))
