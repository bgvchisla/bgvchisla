#!/usr/bin/env python3
"""Refresh selected public Eurostat series for bgvchisla.com.
Only validated observations are written; failed datasets retain their last good values.
"""
import json, math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
SPECS=[
 {"id":"gdp_per_capita_current_eur","title":"БВП на човек по текущи цени","unit":"евро на човек","dataset":"nama_10_pc","filters":{"freq":"A","unit":"CP_EUR_HAB","na_item":"B1GQ","geo":"BG"},"note":"По текущи цени; не измерва самостоятелно реалния растеж."},
 {"id":"gdp_real_growth","title":"Реален БВП — годишен темп на изменение","unit":"%","dataset":"nama_10_gdp","filters":{"freq":"A","unit":"CLV_PCH_PRE","na_item":"B1GQ","geo":"BG"},"note":"Годишен процентен темп при верижно свързани обеми."},
 {"id":"employment_rate_20_64","title":"Заетост на населението 20–64 г.","unit":"%","dataset":"lfsi_emp_a","filters":{"freq":"A","unit":"PC","sex":"T","age":"Y20-64","geo":"BG"},"note":"Коефициент на заетост за възраст 20–64 години."},
 {"id":"unemployment_rate_15_74","title":"Безработица 15–74 г.","unit":"%","dataset":"une_rt_a","filters":{"freq":"A","unit":"PC_ACT","sex":"T","age":"Y15-74","geo":"BG"},"note":"Годишен коефициент на безработица."},
 {"id":"population_total","title":"Население към 1 януари","unit":"души","dataset":"demo_pjan","filters":{"freq":"A","unit":"NR","sex":"T","age":"TOTAL","geo":"BG"},"note":"Население към 1 януари; отчетени стойности."},
 {"id":"gdp_pps_index","title":"БВП на човек в PPS, ЕС = 100","unit":"индекс","dataset":"tec00114","filters":{"freq":"A","unit":"PPS_EU27_2020_HAB","na_item":"B1GQ","geo":"BG"},"note":"Индекс спрямо средното за ЕС (ЕС=100)."},
]
def get_item(obj,index):
 if isinstance(obj,list): return obj[index] if index<len(obj) else None
 return obj.get(str(index)) if isinstance(obj,dict) else None
def parse(spec):
 url=BASE+spec["dataset"]+"?"+urlencode({"lang":"EN",**spec["filters"]})
 req=Request(url,headers={"User-Agent":"bgvchisla-data-updater/1.0","Accept":"application/json"})
 with urlopen(req,timeout=90) as response: data=json.load(response)
 if "error" in data or "time" not in data.get("dimension",{}): raise RuntimeError("Невалиден JSON-stat отговор")
 ids=data.get("id",[]); sizes=data.get("size",[])
 for dim,size in zip(ids,sizes):
  if dim!="time" and size!=1: raise RuntimeError("Заявката връща повече от една серия: "+dim)
 ti=data["dimension"]["time"]["category"]["index"]
 if isinstance(ti,list): ti={str(y):i for i,y in enumerate(ti)}
 vals=data.get("value",{}); flags=data.get("status",{})
 points=[]
 for year,index in sorted(ti.items(),key=lambda x:int(x[0])):
  value=get_item(vals,index)
  if value is None: continue
  if not isinstance(value,(int,float)) or not math.isfinite(value): raise RuntimeError("Невалидна стойност")
  points.append({"year":int(year),"value":value,"flag":get_item(flags,index)})
 if len(points)<2: raise RuntimeError("Недостатъчно наблюдения")
 return {"id":spec["id"],"title":spec["title"],"unit":spec["unit"],"frequency":"annual","source":"Евростат","dataset":spec["dataset"],"source_url":url,"note":spec["note"],"updated_at":datetime.now(timezone.utc).isoformat(),"points":points}
path=Path("economy.json"); economy=json.loads(path.read_text(encoding="utf-8")); old={s["id"]:s for s in economy.get("series",[])}
success=[]
for spec in SPECS:
 try:
  series=parse(spec);old[series["id"]]=series;success.append(spec["id"]);print("OK",spec["id"],len(series["points"]))
 except Exception as exc:
  print("WARN",spec["id"],str(exc))
if not success and not old: raise RuntimeError("Няма нито една валидна серия")
economy["series"]=list(old.values())
economy["last_successful_update"]=datetime.now(timezone.utc).isoformat()
economy["update_status"]={"status":"partial" if len(success)<len(SPECS) else "ok","successful_series":success,"configured_series":len(SPECS)}
tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(economy,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");tmp.replace(path)
