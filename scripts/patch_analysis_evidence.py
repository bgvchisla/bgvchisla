#!/usr/bin/env python3
"""Включва проверения редакционен селектор в разархивирания генератор."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_analysis.py"

def main():
    if not GENERATOR.exists():
        raise SystemExit("Липсва разархивираният генератор на анализи.")

    source = GENERATOR.read_text(encoding="utf-8")
    import_line = "from analysis_evidence import get_evidence as _strict_get_evidence"
    if import_line in source:
        ast.parse(source, filename=str(GENERATOR))
        print("Строгият редакционен селектор вече е включен.")
        return

    start_marker = "def get_evidence(lane):"
    end_marker = "def api(prompt,cfg):"
    if source.count(start_marker) != 1:
        raise SystemExit("Очакваше се точно една функция get_evidence(lane).")
    start = source.index(start_marker)
    end = source.find(end_marker, start)
    if end < 0:
        raise SystemExit("Не е намерена границата преди api(prompt,cfg).")
    replacement = '''from analysis_evidence import get_evidence as _strict_get_evidence

def get_evidence(lane):
    pack = _strict_get_evidence(lane)
    for item in pack["sources"]:
        if str(item.get("source_id", "")).startswith("N"):
            print(
                "ПОДБРАН МАТЕРИАЛ |",
                item.get("editorial_role", ""),
                "|",
                item.get("publisher", ""),
                "|",
                item.get("published", ""),
                "|",
                item.get("title", ""),
                "|",
                item.get("url", ""),
            )
    return pack


'''
    patched = source[:start] + replacement + source[end:]
    ast.parse(patched, filename=str(GENERATOR))
    GENERATOR.write_text(patched, encoding="utf-8")
    print("Включен е строгият редакционен селектор. Синтаксисът е валиден.")

if __name__ == "__main__":
    main()
