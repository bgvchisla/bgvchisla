import urllib.request
from pathlib import Path
URL = "https://www.minfin.bg/upload/65481/BULETIN_September%2B_2026.pdf"
req = urllib.request.Request(URL, headers={"User-Agent":"Mozilla/5.0 (compatible; Bgvchisla/1.0)"})
with urllib.request.urlopen(req, timeout=60) as response:
    raw = response.read()
    print("HTTP", response.status, "CONTENT_TYPE", response.headers.get("Content-Type"))
if not raw.startswith(b"%PDF-"):
    raise SystemExit(f"Official PDF endpoint did not return a PDF: {raw[:100]!r}")
Path("/tmp/minfin-september-2026.pdf").write_bytes(raw)
print("OFFICIAL_PDF_OK", len(raw), "bytes")
try:
    from pypdf import PdfReader
    reader=PdfReader("/tmp/minfin-september-2026.pdf")
    print("PAGES",len(reader.pages))
    text="\n".join((p.extract_text() or "") for p in reader.pages)
    print("TEXT_CHARS",len(text))
    for term in ["33 898,5","37 567,7","3 669,2","Приходите","Разходите"]:
        print("TERM",repr(term),"FOUND",term in text)
    print(text[:12000])
except Exception as exc:
    raise SystemExit(f"PDF readable test failed: {exc}")
