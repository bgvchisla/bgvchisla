#!/usr/bin/env python3
"""Adds a visible, idempotent AI-transparency notice to a generated article."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", required=True, choices=("bulgaria", "world"))
    parser.add_argument("--before", default="/tmp/articles-before.json")
    args = parser.parse_args()
    registry = json.loads((ROOT / "analizi" / "articles.json").read_text(encoding="utf-8"))
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    old = {str(row.get("slug", "")) for row in before}
    new_rows = [row for row in registry if row.get("lane") == args.lane and str(row.get("slug", "")) not in old]
    if len(new_rows) != 1: raise SystemExit(f"Очаква се точно един нов анализ; намерени са {len(new_rows)}.")
    row = new_rows[0]
    path = ROOT / "analizi" / str(row["slug"]) / "index.html"
    page = path.read_text(encoding="utf-8")
    if 'class="ai-disclosure"' in page: raise SystemExit("AI disclosure вече съществува; отказвам повторно инжектиране.")
    css = """
.ai-disclosure{margin:0 0 22px;padding:13px 16px;background:#e8edf3;border:1px solid #cbd6e1;border-left:4px solid #315f91;border-radius:9px;color:#24384f;font-size:.82rem;line-height:1.5}
.ai-disclosure strong{color:#24384f}
"""
    disclosure = """<div class="ai-disclosure" role="note" aria-label="Прозрачност относно изкуствения интелект"><strong>Прозрачност:</strong> Този анализ е генериран с помощта на изкуствен интелект (GPT-6 Luna). За публикуване се изисква успешна независима автоматизирана фактологична проверка с Google Gemini 3.8 Flash чрез директно извличане и съпоставка с посочените първични източници (URL Context). Не е преминал човешка редакционна проверка.</div>"""
    if "</style>" not in page: raise SystemExit("Липсва style блок.")
    page = page.replace("</style>", css + "\n</style>", 1)
    byline = re.search(r'(<div class="byline"[^>]*>[\s\S]*?</div>)', page, flags=re.I)
    if not byline: raise SystemExit("Липсва byline позиция.")
    page = page[:byline.end()] + "\n" + disclosure + page[byline.end():]
    page = page.replace('<html lang="bg">', '<html lang="bg" data-ai-generated="true">', 1)
    path.write_text(page, encoding="utf-8")
    print(f"Добавен е видим AI disclosure за {row['slug']}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
