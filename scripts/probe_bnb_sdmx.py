#!/usr/bin/env python3
"""Inspect row labels and latest observations in the official BNB workbook."""
import io, urllib.request
from openpyxl import load_workbook
URL="https://www.bnb.bg/bnbweb/groups/public/documents/bnb_download/s_monetarystatistics_all_bg.xlsx"
req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 bgvchisla official data probe"})
with urllib.request.urlopen(req,timeout=60) as r:
    raw=r.read(50_000_001)
if len(raw)>50_000_000 or not raw.startswith(b"PK"): raise SystemExit("Invalid XLSX")
wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
for name in ["Cred_BG","BNB Dynamic","OMFIs_Stat balance","BNB_Stat Balance"]:
    ws=wb[name]
    print("\n###",name,"rows",ws.max_row,"cols",ws.max_column)
    if name in ["Cred_BG","BNB Dynamic"]:
        # Monthly series are arranged as labels in col A and periods from col B onward.
        dates=[ws.cell(2,c).value for c in range(2,ws.max_column+1)]
        valid=[(c,v) for c,v in zip(range(2,ws.max_column+1),dates) if v is not None]
        print("DATE RANGE",valid[0] if valid else None,valid[-1] if valid else None)
        last_col=valid[-1][0] if valid else ws.max_column
        for i in range(3,ws.max_row+1):
            label=ws.cell(i,1).value
            val=ws.cell(i,last_col).value
            if label is not None:
                print("ROW",i,repr(label),"LATEST",repr(val))
    else:
        for i in range(7,ws.max_row+1):
            label=ws.cell(i,1).value
            val=ws.cell(i,2).value
            if label is not None:
                print("ROW",i,repr(label),"TOTAL",repr(val))
