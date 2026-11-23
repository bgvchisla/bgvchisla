#!/usr/bin/env python3
"""Independent, fail-closed fact check for AI-authored editorial analyses."""
from __future__ import annotations
import argparse, datetime as dt, html, json, os, re, sys, tempfile, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "analysis" / "config.json"
OPENAI_LEDGER_PATH = ROOT / "analysis" / "monthly_usage.json"
LEDGER_PATH = ROOT / "analysis" / "verification_usage.json"
REGISTRY_PATH = ROOT / "analizi" / "articles.json"

def read_json(path: Path, default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding="utf-8"))

def write_json_atomic(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2); handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)

def month_key(now): return now.strftime("%Y-%m")

def prices(config, now):
    if now.date() < dt.date(2027, 1, 1):
        return float(config["review_input_usd_per_million_until_2026_12_31"]), float(config["review_output_usd_per_million_until_2026_12_31"])
    return float(config["review_input_usd_per_million_from_2027_01_01"]), float(config["review_output_usd_per_million_from_2027_01_01"])

def canonical_url(value):
    try:
        p = urlsplit(value.strip())
        if p.scheme not in {"http", "https"} or not p.hostname: return ""
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme.lower()}://{p.hostname.lower()}{port}{p.path.rstrip('/')}"
    except Exception: return ""

def normalized_domain(value):
    try:
        host = str(value or "").strip().lower().split("/")[0].split(":")[0].strip(".")
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

def is_official_domain(host, approved):
    return any(host == domain or host.endswith("." + domain) for domain in approved)

def extract_page_text(page):
    match = re.search(r"<main\b[^>]*>(.*?)</main>", page, flags=re.I | re.S)
    source = match.group(1) if match else page
    source = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<(nav|footer)\b[^>]*>.*?</\1>", " ", source, flags=re.I | re.S)
    source = re.sub(r'<ol\b[^>]*class="source-list"[^>]*>.*?</ol>', " ", source, flags=re.I | re.S)
    source = re.sub(r"<sup\b[^>]*>.*?</sup>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<[^>]+>", " ", source)
    return re.sub(r"\s+", " ", html.unescape(source)).strip()

def latest_article(slug):
    rows = read_json(REGISTRY_PATH, [])
    row = next((item for item in rows if item.get("slug") == slug), None)
    if not row: raise ValueError(f"Няма регистриран анализ със slug {slug!r}.")
    path = ROOT / "analizi" / slug / "index.html"
    if not path.is_file(): raise ValueError(f"Липсва HTML на анализа: {path}")
    page = path.read_text(encoding="utf-8"); text = extract_page_text(page)
    if len(text) < 2500: raise ValueError("Текстът на анализа е твърде кратък за независима проверка.")
    if len(text) > int(read_json(CONFIG_PATH, {}).get("maximum_review_characters", 50000)):
        raise ValueError("Текстът надхвърля защитния лимит за проверка.")
    if not isinstance(row.get("source_urls"), list) or len(row["source_urls"]) < 4:
        raise ValueError("Липсват достатъчно изходни URL адреси в регистъра.")
    return row, page, text

def load_ledger(now):
    ledger = read_json(LEDGER_PATH, {})
    if ledger.get("month") != month_key(now):
        ledger = {"month": month_key(now), "calls": 0, "spent_usd": 0.0, "reserved_usd": 0.0, "history": []}
    for k, v in {"history": [], "calls": 0, "spent_usd": 0.0, "reserved_usd": 0.0, "google_search_queries": 0}.items(): ledger.setdefault(k, v)
    return ledger

def reserve_budget(config, ledger, now):
    if int(ledger["calls"]) >= int(config["max_factcheck_calls_per_month"]):
        raise RuntimeError("Достигнат е месечният лимит за независими проверки.")
    openai = read_json(OPENAI_LEDGER_PATH, {})
    openai_spend = float(openai.get("spent_usd", 0.0)) if openai.get("month") == month_key(now) else 0.0
    review_spend, review_reserved = float(ledger["spent_usd"]), float(ledger["reserved_usd"])
    in_price, out_price = prices(config, now)
    token_reserve = (int(config["maximum_review_input_tokens"]) * in_price + int(config["maximum_review_output_tokens"]) * out_price) / 1_000_000
    search_reserve = int(config["max_search_queries_per_call"]) * float(config["google_search_usd_per_1000_queries"]) / 1000
    reserve = token_reserve + search_reserve
    if review_spend + review_reserved + reserve > float(config["review_monthly_budget_usd"]):
        raise RuntimeError("Проверката би превишила отделния си месечен бюджет.")
    if openai_spend + review_spend + review_reserved + reserve > float(config["monthly_total_budget_usd"]):
        raise RuntimeError("Проверката би превишила общия бюджет на двата модела.")
    return round(reserve, 8)

def build_prompt(row, article_text, config):
    sources = json.dumps(row.get("source_urls", []), ensure_ascii=False, indent=2)
    official_domains = json.dumps(config.get("official_source_domains", []), ensure_ascii=False)
    return f"""РОЛЯ: Ти си независим външен проверяващ на факти за българско финансово-икономическо издание. Не си авторът. Авторът е GPT-6 Luna (OpenAI). Провери текста чрез Google Search и първични източници.

ЗАДЪЛЖИТЕЛНА МЕТОДИКА:
1. Не приемай твърдение за вярно само защото е в текста или има посочен URL.
2. Използвай Google Search за независимо търсене. Приоритет са оригинални източници: НСИ, БНБ, НОИ, МФ, Евростат, ЕК, ЕЦБ, Съвет на ЕС, Фед, BIS, IMF, World Bank, WTO и други релевантни институции.
3. Провери всяко съществено фактическо твърдение, всяко число, процент, промяна, прогноза, дата, период, единица, валута, знаменател/база и изчисление. Провери причинно-следствените заключения; разграничи факт, прогноза, мнение и интерпретация.
4. За числовите твърдения сравни оригиналната таблица/серия или официалния документ. Не смесвай несъпоставими методологии (напр. КФП и ЕСС 2010; месечна и годишна инфлация).
5. За всяко твърдение върни кратък цитат от статията, тип, важност, verdict, точен URL от реалните Google Search grounding резултати и кратка обосновка.
6. Не измисляй източници или проверки. При липса на доказателство върни unverifiable.
7. Съществено противоречие/грешна числова стойност означава FAIL. Липсващо доказателство, непълно покритие или методологична неяснота означава REVIEW. PASS само когато всички съществени твърдения са потвърдени и числовият одит е пълен.
8. Минимум 8 съществени проверени твърдения, 4 различни grounding източника и минимум 2 различни официални първични домейна от списъка: {official_domains}. Ако няма достатъчно — REVIEW.
9. Ограничѝ Google Search до максимум 4 конкретни заявки; групирай темите, без да пропускаш съществените твърдения. Ако е нужна по-широка проверка, върни REVIEW и посочи ограниченията.
10. Върни САМО валиден JSON, без Markdown.

ФОРМАТ:
{{
 "overall_verdict":"PASS | REVIEW | FAIL",
 "summary":"резюме на български",
 "claims_checked":[{{"claim_id":"C1","claim_text":"кратък точен цитат","claim_type":"numeric | date | comparison | forecast | causal | qualitative","severity":"critical | major | minor","verdict":"verified | partially_verified | contradicted | unverifiable","evidence_urls":["https://..."],"evidence_summary":"доказателство","correction":""}}],
 "numerical_audit":{{"numeric_claims_found":0,"numeric_claims_verified":0,"issues":[]}},
 "methodology_issues":[],
 "limitations":[]
}}

КАНДИДАТ-ИЗТОЧНИЦИ (не ги приемай за доказателство преди проверка):
{sources}

ЗАГЛАВИЕ: {row.get("title","")}
НАПРАВЛЕНИЕ: {row.get("lane","")}

ПЪЛЕН ТЕКСТ НА АНАЛИЗА:
{article_text}
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--report", default="analysis/factcheck_report.json")
    args = parser.parse_args()
    config = read_json(CONFIG_PATH, {})
    model = str(config.get("review_model", ""))
    if model != "gemini-3.8-flash": raise SystemExit("Невалиден фиксиран проверяващ модел.")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key: raise SystemExit("Липсва GEMINI_API_KEY; независимата проверка е блокирана.")
    if os.environ.get("ANALYSES_PUBLISH_ENABLED", "").lower() != "true":
        raise SystemExit("ANALYSES_PUBLISH_ENABLED не е true; платената проверка е блокирана.")
    now = dt.datetime.now(dt.timezone.utc)
    ledger = load_ledger(now); reserve = reserve_budget(config, ledger, now)
    row, _page, article_text = latest_article(args.slug)
    ledger["calls"] = int(ledger["calls"]) + 1
    ledger["reserved_usd"] = round(float(ledger["reserved_usd"]) + reserve, 8)
    entry = {"attempt": ledger["calls"], "slug": args.slug, "model": model, "timestamp_utc": now.isoformat(), "reserved_usd": reserve, "status": "reserved"}
    ledger["history"].append(entry); write_json_atomic(LEDGER_PATH, ledger)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": build_prompt(row, article_text, config)}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": int(config["maximum_review_output_tokens"]),
            "thinkingConfig": {"thinkingLevel": str(config.get("review_reasoning_effort", "medium")).upper()}
        }
    }
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        usage = response_payload.get("usageMetadata", {})
        prompt_tokens = int(usage.get("promptTokenCount", 0) or 0)
        output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        thinking_tokens = int(usage.get("thoughtsTokenCount", 0) or 0)
        billable_output_tokens = output_tokens + thinking_tokens
        in_price, out_price = prices(config, now)
        actual_cost = round((prompt_tokens * in_price + billable_output_tokens * out_price) / 1_000_000, 8) if (prompt_tokens or billable_output_tokens) else reserve
        candidate = (response_payload.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        response_text = "\n".join(str(p.get("text", "")) for p in parts if p.get("text"))
        grounding_metadata = candidate.get("groundingMetadata") or {}
        grounding = grounding_metadata.get("groundingChunks") or []
        web_search_queries = grounding_metadata.get("webSearchQueries") or []
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
        ledger["reserved_usd"] = round(max(0.0, float(ledger["reserved_usd"]) - reserve), 8)
        ledger["spent_usd"] = round(float(ledger["spent_usd"]) + reserve, 8)
        entry.update({"status": "error_unknown_cost", "estimated_cost_usd": reserve, "error": type(exc).__name__})
        write_json_atomic(LEDGER_PATH, ledger)
        raise SystemExit(f"Независимата проверка не завърши. Публикацията е блокирана. Тип грешка: {type(exc).__name__}") from exc
    search_query_count = len(web_search_queries)
    search_cost = search_query_count * float(config["google_search_usd_per_1000_queries"]) / 1000
    actual_cost = round(actual_cost + search_cost, 8)
    ledger["reserved_usd"] = round(max(0.0, float(ledger["reserved_usd"]) - reserve), 8)
    ledger["spent_usd"] = round(float(ledger["spent_usd"]) + actual_cost, 8)
    ledger["google_search_queries"] = int(ledger.get("google_search_queries", 0)) + search_query_count
    entry.update({"status": "response_received", "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
                  "thinking_tokens": thinking_tokens, "billable_output_tokens": billable_output_tokens,
                  "google_search_queries": search_query_count, "google_search_cost_usd": round(search_cost, 8),
                  "actual_cost_usd": actual_cost})
    write_json_atomic(LEDGER_PATH, ledger)

    try:
        start = response_text.find("{")
        if start < 0: raise ValueError("Липсва JSON.")
        report = json.JSONDecoder().raw_decode(response_text[start:])[0]
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit("Проверяващият модел не върна валиден JSON. Публикацията е блокирана.") from exc

    grounded_urls, official_domains_found = set(), set()
    approved_domains = [normalized_domain(d) for d in config.get("official_source_domains", [])]
    for chunk in grounding:
        web = chunk.get("web") or {}
        uri = canonical_url(str(web.get("uri", "")))
        domain = normalized_domain(web.get("domain") or (urlsplit(uri).hostname if uri else ""))
        if uri: grounded_urls.add(uri)
        if domain and is_official_domain(domain, approved_domains):
            official_domains_found.add(domain)
    claims = report.get("claims_checked", [])
    problems = []
    min_claims = int(config["minimum_verified_claims"])
    min_sources = int(config["minimum_grounding_sources"])
    min_official = int(config["minimum_official_grounding_domains"])
    max_search_call = int(config["max_search_queries_per_call"])
    max_search_month = int(config["max_search_queries_per_month"])
    if len(claims) < min_claims: problems.append(f"Твърденията са {len(claims)}; минимумът е {min_claims}.")
    if len(grounded_urls) < min_sources: problems.append(f"Google grounding източниците са {len(grounded_urls)}; минимумът е {min_sources}.")
    if len(official_domains_found) < min_official: problems.append(f"Официалните първични домейни са {len(official_domains_found)}; минимумът е {min_official}.")
    if search_query_count <= 0: problems.append("Google Search не е изпълнил проверимо търсене.")
    if search_query_count > max_search_call: problems.append(f"Google Search заявките са {search_query_count}; максимумът за една проверка е {max_search_call}.")
    if int(ledger.get("google_search_queries", 0)) > max_search_month: problems.append("Достигнат е месечният лимит за Google Search заявки.")
    if not claims: problems.append("Липсва списък с твърдения.")
    accepted = 0
    for i, claim in enumerate(claims, 1):
        evidence = {canonical_url(str(u)) for u in claim.get("evidence_urls", [])}
        if str(claim.get("verdict", "")).lower() == "verified" and evidence.intersection(grounded_urls):
            accepted += 1
        else:
            problems.append(f"Твърдение {claim.get('claim_id', i)} няма потвърждение от Google grounding източник.")
    numeric = report.get("numerical_audit") or {}
    found, verified = int(numeric.get("numeric_claims_found", 0) or 0), int(numeric.get("numeric_claims_verified", 0) or 0)
    numeric_issues = numeric.get("issues", [])
    if found <= 0 or verified != found or numeric_issues: problems.append("Числовият одит е непълен или съдържа нерешени проблеми.")
    if report.get("methodology_issues"): problems.append("Открити са нерешени методологични проблеми.")
    if accepted < min_claims: problems.append("Няма достатъчно твърдения с независимо доказателство.")
    raw_verdict = str(report.get("overall_verdict", "REVIEW")).upper()
    if raw_verdict == "FAIL" or any(str(c.get("verdict","")).lower()=="contradicted" and str(c.get("severity","")).lower() in {"critical","major"} for c in claims):
        final_verdict = "FAIL"
    elif raw_verdict == "PASS" and not problems:
        final_verdict = "PASS"
    else:
        final_verdict = "REVIEW"
    output = {
        "schema_version":1, "slug":args.slug, "title":row.get("title",""), "lane":row.get("lane",""),
        "review_provider":"Google", "review_model":model, "review_method":"Gemini API with Google Search grounding",
        "timestamp_utc":now.isoformat(), "overall_verdict":final_verdict, "model_verdict":raw_verdict,
        "summary":str(report.get("summary","")), "claims_checked":claims, "verified_claims":accepted,
        "numeric_claims_found":found, "numeric_claims_verified":verified, "grounded_sources":sorted(grounded_urls),
        "grounded_source_count":len(grounded_urls), "official_grounding_domains":sorted(official_domains_found),
        "official_grounding_domain_count":len(official_domains_found), "google_search_queries":web_search_queries,
        "google_search_query_count":search_query_count, "google_search_cost_usd":round(search_cost,8),
        "methodology_issues":report.get("methodology_issues",[]),
        "limitations":report.get("limitations",[]), "blocking_reasons":problems,
        "cost_usd":actual_cost, "billable_output_tokens":billable_output_tokens, "thinking_tokens":thinking_tokens,
        "reasoning_effort":str(config.get("review_reasoning_effort","medium")).upper(),
        "usage":response_payload.get("usageMetadata",{})
    }
    write_json_atomic(ROOT / args.report, output)
    print(f"Независима проверка: {final_verdict}; твърдения: {accepted}/{len(claims)}; числа: {verified}/{found}; grounding източници: {len(grounded_urls)}; официални домейни: {len(official_domains_found)}; Google Search заявки: {search_query_count}; reasoning tokens: {thinking_tokens}; обща цена USD: {actual_cost:.6f}.")
    print(f"Отчет: {args.report}")
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a", encoding="utf-8") as handle:
        handle.write(f"verdict={final_verdict}\nverified_claims={accepted}\ngrounded_sources={len(grounded_urls)}\nofficial_domains={len(official_domains_found)}\ngoogle_search_queries={search_query_count}\ncost_usd={actual_cost:.8f}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
