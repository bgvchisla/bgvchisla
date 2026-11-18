import urllib.request,re
from html.parser import HTMLParser
import xlrd
PAGE="https://www.minfin.bg/bg/statistics/5"
class P(HTMLParser):
 def __init__(self): super().__init__(); self.href=None; self.parts=[]; self.links=[]
 def handle_starttag(self,t,a):
  if t=="a": self.href=dict(a).get("href"); self.parts=[]
 def handle_data(self,d):
  if self.href is not None:self.parts.append(d)
 def handle_endtag(self,t):
  if t=="a" and self.href is not None:self.links.append((self.href," ".join(self.parts).strip()));self.href=None
req=urllib.request.Request(PAGE,headers={"User-Agent":"Mozilla/5.0"})
html=urllib.request.urlopen(req,timeout=60).read().decode("utf-8","replace")
p=P();p.feed(html)
matches=[]
for href,label in p.links:
 if "Септември 2026" in label or "септември 2026" in label.lower():
  if href.startswith("/"):href="https://www.minfin.bg"+href
  matches.append((href,label))
print("MATCHES",matches)
if not matches: raise SystemExit("No September 2026 XLS link found")
url=matches[0][0]
req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
raw=urllib.request.urlopen(req,timeout=60).read()
print("XLS",url,"BYTES",len(raw),"HEADER",raw[:8])
wb=xlrd.open_workbook(file_contents=raw)
print("SHEETS",wb.sheet_names())
for sh in wb.sheets():
 print("\nSHEET",sh.name,"ROWS",sh.nrows,"COLS",sh.ncols)
 for i in range(min(sh.nrows,45)):
  vals=[sh.cell_value(i,j) for j in range(min(sh.ncols,10))]
  if any(str(x).strip() for x in vals): print("ROW",i+1,repr(vals))
