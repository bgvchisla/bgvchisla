#!/usr/bin/env python3
"""Import monthly business-climate indicators from official NSI press releases."""
import datetime as dt, html, json, re, urllib.request
from html.parser import HTMLParser
from pathlib import Path

INDEX="https://www.nsi.bg/press-release"
BASE="https://www.nsi.bg"
OUT=Path("official_business_climate.json")
UA="Mozilla/5.0 (compatible; Bgvchisla/1.0)"

class Page(HTMLParser):
    def __init__(self): super().__init__(); self.href=None; self.buf=[]; self.links=[]; self.text=[]
    def handle_starttag(self,t,a):
        if t=="a": self.href=dict(a).get("href"); self.buf=[]
    def handle_data(self,d):
        self.text.append(d)
        if self.href is not None:self.buf.append(d)
    def handle_endtag(self,t):
        if t=="a" and self.href is not None:
            self.links.append((self.href," ".join(self.buf))); self.href=None; self.buf=[]

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read().decode("utf-8","replace")

def absolute(u): return u if u.startswith("http") else BASE+u

def parse_pair(text, label):
    # Extract the two official values stated as "от X на Y" in the sector paragraph.
    patterns={
      "total":r"общият показател на бизнес климата.*?\(от\s*(-?\d+[.,]\d+)\s*%\s*на\s*(-?\d+[.,]\d+)\s*%\)",
      "industry":r"бизнес климат в промишлеността.*?\(от\s*(-?\d+[.,]\d+)\s*%\s*на\s*(-?\d+[.,]\d+)\s*%\)",
      "construction":r"бизнес климат в строителството.*?\(от\s*(-?\d+[.,]\d+)\s*%\s*на\s*(-?\d+[.,]\d+)\s*%\)",
      "retail":r"бизнес климат в търговията на дребно.*?\(от\s*(-?\d+[.,]\d+)\s*%\s*на\s*(-?\d+[.,]\d+)\s*%\)",
      "services":r"бизнес климат в сектора на услугите.*?\(от\s*(-?\d+[.,]\d+)\s*%\s*на\s*(-?\d+[.,]\d+)\s*%\)"
    }
    out={}
    for key,pat in patterns.items():
        m=re.search(pat,text,re.I|re.S)
        if not m: raise ValueError("Cannot extract official previous/current values for "+key)
        prev,cur=[float(x.replace(",",".")) for x in m.groups()]
        out[key]={"value":cur,"previous":prev,"change":round(cur-prev,1)}
    return out

def main():
    page=Page(); page.feed(get(INDEX))
    links=[]
    for href,title in page.links:
        title=html.unescape(title)
        if "/press-release/" in href and "nablyudenie-na-biznes-tendenciite" in href.lower():
            links.append(absolute(href))
    # Prefer latest dated release, not an arbitrary first link.
    urls=list(dict.fromkeys(links))
    if not urls: urls=["https://www.nsi.bg/press-release/nablyudenie-na-biznes-tendenciite-v-promishlenostta-stroitelstvoto-targoviyata-na-drebno-i-uslugite-9194"]
    if not urls: raise ValueError("No official NSI business-climate release links found")
    old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"history":[]}
    olddate=old.get("reference_date","")
    chosen=None
    for url in urls[:20]:
        raw=get(url)
        p=Page();p.feed(raw)
        text=" ".join(p.text)
        m=re.search(r"(?:м\.?\s*)?(януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември)\s+(20\d{2})\s+год",text,re.I)
        if not m: continue
        months={"януари":"01","февруари":"02","март":"03","април":"04","май":"05","юни":"06","юли":"07","август":"08","септември":"09","октомври":"10","ноември":"11","декември":"12"}
        period=m.group(2)+"-"+months[m.group(1).lower()]
        if period<olddate: continue
        try: values=parse_pair(text,"")
        except ValueError: continue
        chosen={"period":period,"url":url,"values":values}
        break
    if not chosen: raise ValueError("No newer complete official NSI monthly release with all five indicators")
    history=[x for x in old.get("history",[]) if x.get("period")!=chosen["period"]]
    history.append({"period":chosen["period"],"values":chosen["values"],"source_url":chosen["url"]})
    history=sorted(history,key=lambda x:x["period"])[-120:]
    payload={"source":"Национален статистически институт","source_url":chosen["url"],"reference_date":chosen["period"],"updated_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"values":chosen["values"],"history":history,"methodology":"Показателите са балансови оценки от месечното наблюдение на бизнес тенденциите. Общият показател е претеглена средна на четирите отраслови показателя. Промените са разлики в процентни пунктове спрямо предходния месец."}
    if old.get("reference_date")==payload["reference_date"] and old.get("values")==payload["values"]:
        payload["updated_at"]=old.get("updated_at",payload["updated_at"])
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("NSI business climate OK",payload["reference_date"],payload["values"])

if __name__=="__main__":main()
