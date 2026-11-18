#!/usr/bin/env python3
"""Import key pension statistics from the latest official NSSI XLS bulletin."""
import datetime as dt
import html
import json
import math
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
import xlrd

PAGE = "https://nssi.bg/publikacii/statistika/pensii-statistika/"
OUT = Path("official_nssi.json")

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.href=None; self.parts=[]; self.items=[]
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href=dict(attrs).get("href"); self.parts=[]
    def handle_data(self, data):
        if self.href is not None: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.items.append((self.href, " ".join(self.parts).strip()))
            self.href=None; self.parts=[]

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; Bgvchisla/1.0)"})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read()

def number(sheet, row, value_col, expected_label, label_col=1):
    label=str(sheet.cell_value(row-1,label_col-1)).strip()
    if label != expected_label: raise ValueError(f"Unexpected NSSI label at {sheet.name}!R{row}C{label_col}: {label!r}")
    value=sheet.cell_value(row-1,value_col-1)
    value=float(value)
    if not math.isfinite(value) or value < 0: raise ValueError(f"Invalid numeric value: {value}")
    return value

def extract_counts(raw, source_url):
    book=xlrd.open_workbook(file_contents=raw)
    required={"brv","brp","SRRAZ","razhod"}
    if not required.issubset(set(book.sheet_names())):
        raise ValueError(f"Missing expected NSSI sheets in {source_url}: {required-set(book.sheet_names())}")
    for sheet_name, title_fragment in [("brv","Брой на пенсионерите"),("brp","Брой на пенсиите"),("SRRAZ","Среден брой пенсионери"),("razhod","Разход по видове пенсии")]:
        title=str(book.sheet_by_name(sheet_name).cell_value(2,0)).replace("\\n"," ")
        if title_fragment not in title: raise ValueError(f"Unexpected table title in {sheet_name}: {title!r}")
    pensioners=number(book.sheet_by_name("brv"),9,2,"Общо ( І + ІІ + ІІІ + IV )")
    pensions=number(book.sheet_by_name("brp"),9,2,"Общо ( І + ІІ + ІІІ + IV )")
    avg=number(book.sheet_by_name("SRRAZ"),7,4,"Общо ( І + ІІ + ІІІ + IV)",label_col=1)
    expenditure=number(book.sheet_by_name("razhod"),9,2,"Разход за пенсии")
    return {"pensioners":int(pensioners),"pensions":int(pensions),"average_pension":round(avg,2),"pension_expenditure":round(expenditure,2)}

def main():
    page=fetch(PAGE).decode("utf-8","replace")
    parser=Links(); parser.feed(page)
    candidates=[]
    seen=set()
    for href,label in parser.items:
        text=html.unescape(label)
        if "Статистически бюлетин" not in text or "Пенсии" not in text or not re.search(r"\\.xls(?:\\?|$)",href,re.I): continue
        m=re.search(r"(\\d{2})\\.(\\d{2})\\.(\\d{4})",text)
        if not m: continue
        date=dt.date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        if date.year < 2025: continue
        if href.startswith("/"): href="https://nssi.bg"+href
        elif href.startswith("//"): href="https:"+href
        if href in seen: continue
        seen.add(href)
        candidates.append((date,href,text))
    if not candidates:
        raise ValueError("No dated official NSSI pension XLS bulletins for 2025 onward found")
    candidates.sort(key=lambda x:x[0])
    history=[]
    latest=None
    for period,url,label in candidates:
        values=extract_counts(fetch(url),url)
        history.append({
            "reference_date":period.isoformat(),
            "pensioners_count":values["pensioners"],
            "pensions_count":values["pensions"],
            "source_url":url,
            "bulletin":label
        })
        latest=(period,url,label,values)
        print("Validated NSSI bulletin",period.isoformat(),values["pensioners"],values["pensions"])
    if len(history)<6:
        raise ValueError(f"Expected at least 6 quarterly historical bulletins from 2025 onward, found {len(history)}")
    period,url,label,values=latest
    previous=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    period_iso=period.isoformat()
    if previous and period_iso < previous.get("reference_date",""):
        raise ValueError("NSSI data regression: refusing to replace newer bulletin")
    payload={
      "source":"Национален осигурителен институт",
      "source_url":PAGE,
      "workbook_url":url,
      "dataset":"Статистически бюлетин „Пенсии“",
      "reference_date":period_iso,
      "bulletin":label,
      "updated_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
      "metrics":{
        "pensioners_count":{"label":"Брой пенсионери","value":values["pensioners"],"unit":"лица","period_type":"към датата"},
        "pensions_count":{"label":"Брой пенсии","value":values["pensions"],"unit":"пенсии","period_type":"към датата"},
        "average_pension":{"label":"Среден размер на пенсията на един пенсионер","value":values["average_pension"],"unit":"евро","period_type":"средно за отчетното полугодие"},
        "pension_expenditure":{"label":"Разход за пенсии","value":values["pension_expenditure"],"unit":"евро","period_type":"натрупано от началото на годината до датата"}
      },
      "history":history,
      "methodology":"Броят на пенсионерите и пенсиите е моментна стойност към отчетната дата. Историческата серия включва само тези съпоставими количествени показатели от официалните тримесечни бюлетини. Средният размер е среден за отчетния период. Разходът е натрупан от началото на годината до отчетната дата; показателите имат различна времева база и не следва да се сравняват като еднотипни месечни стойности.",
      "history_methodology":"Историческите редове са броят на пенсионерите и броят на пенсиите към датите на съответните тримесечни бюлетини. Паричните показатели не са включени в историческата серия, за да не се смесват валути и отчетни периоди."
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    print("NSSI import OK",period_iso,"history points",len(history))
    for k,v in payload["metrics"].items(): print(k,v)


if __name__=="__main__": main()
