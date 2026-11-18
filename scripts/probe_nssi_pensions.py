import io, urllib.request
import xlrd
URLS=[
 "https://nssi.bg/wp-content/uploads/STATB22026.xls",
 "https://nssi.bg/wp-content/uploads/STATB12026.xls",
]
for url in URLS:
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=60) as r: raw=r.read()
        print("URL",url,"BYTES",len(raw),"HEADER",raw[:8])
        book=xlrd.open_workbook(file_contents=raw)
        print("SHEETS",book.sheet_names())
        for sh in book.sheets():
            print("SHEET",sh.name,"ROWS",sh.nrows,"COLS",sh.ncols)
            for row in range(min(12,sh.nrows)):
                vals=[sh.cell_value(row,col) for col in range(min(8,sh.ncols))]
                print("ROW",row+1,repr(vals))
        break
    except Exception as e:
        print("FAILED",url,type(e).__name__,str(e))
