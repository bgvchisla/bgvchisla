#!/usr/bin/env python3
"""Inspect the official BNB SDMX-ML DCS publication without publishing observations."""
import urllib.request
import xml.etree.ElementTree as ET

URL = "https://www.bnb.bg/bnbweb/groups/public/documents/bnb_sdmx/dcs.xml"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 bgvchisla official data probe"})
with urllib.request.urlopen(req, timeout=60) as response:
    raw = response.read(30_000_001)
    print("HTTP", response.status, "content-type", response.headers.get("Content-Type"), "bytes", len(raw))
if len(raw) > 30_000_000:
    raise SystemExit("Response exceeds 30 MB safety limit")
root = ET.fromstring(raw)
print("ROOT", root.tag)
print("ROOT ATTRS", root.attrib)
for child in list(root)[:12]:
    print("CHILD", child.tag, child.attrib)
ns = {"generic": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"}
# Generic and compact SDMX structures are inspected generically.
for elem in root.iter():
    local = elem.tag.rsplit("}", 1)[-1]
    if local in {"DataSet", "Series", "Obs", "ObsDimension", "ObsValue", "Group", "KeyFamilyRef", "Dataflow"}:
        print("ELEMENT", local, elem.attrib, (elem.text or "").strip()[:160])
print("TOTAL ELEMENTS", sum(1 for _ in root.iter()))
