#!/usr/bin/env python3
"""
Stock Market News Digest — 日美股市新闻播报
Based on AI News Digest Automation Template v2
Dependencies: pip install google-genai
"""
import html, os, subprocess, re, sys, time, json, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from pathlib import Path

from article_summaries import enrich_articles, summarize_articles, summary_quality_issues

# ╔═══════════════════════════════════════════════════════════╗
# ║  CONFIG — 日美股市新闻播报                                 ║
# ╚═══════════════════════════════════════════════════════════╝
CONFIG = {
    "title": "Stock Market Daily",
    "emoji": "📈",
    "github_user": "roboticsdao",
    "github_repo": "stock-market-daily",
    "tz_offset": 9,
    "sections": [
        {
            "emoji": "🇺🇸",
            "label": "美国股市 / US Market",
            "keywords": "US stock market S&P500 NASDAQ Dow Jones NYSE earnings Fed rate cut Wall Street tech stocks NVIDIA Apple Microsoft Amazon Tesla",
            "rss_queries": [
                "Nvidia Micron AMD Qualcomm AI chip stocks today shares earnings",
                "Nvidia stock today AI chips Nasdaq Wall Street",
                "Apple stock today Micron tech rally price hikes Nasdaq",
                "Tesla stock today Wall Street shares analyst",
                "AI chip stocks today Nvidia Broadcom AMD Micron semiconductor shares",
                "US stock movers today technology AI earnings analyst upgrade downgrade",
                "Magnificent Seven stocks today Nvidia Tesla Apple Microsoft Amazon Meta Alphabet",
                "United States stock market sectors technology stocks today",
            ],
            "exclude_terms": ["ETF", "Vanguard", "SpaceX", "No-Brainer Buy", "Better Buy", "over the past decade"],
        },
        {
            "emoji": "🇯🇵",
            "label": "日本株式市場 / Japan Market",
            "keywords": "Japan stock market Nikkei 225 TOPIX 日経平均 東証 日本株 日銀 金利 円安 半導体 トヨタ ソニー 決算",
            "rss_queries": [
                "日経平均 日本株 個別銘柄 半導体 AI ソフトバンク 東京エレクトロン アドバンテスト",
                "日本株 値上がり 値下がり 銘柄 決算 レーティング",
                "東京エレクトロン アドバンテスト 半導体株 日経平均",
                "ソフトバンクグループ 株価 AI データセンター",
                "トヨタ ソニー 任天堂 日本株 今日",
            ],
            "exclude_terms": ["ETF", "投資信託"],
        },
        {
            "emoji": "🌍",
            "label": "宏观经济与投资 / Macro & Investment",
            "keywords": "global economy GDP inflation interest rate central bank bond yield currency forex USD JPY trade tariff oil gold crypto Bitcoin ETF",
            "rss_queries": [
                "global markets today dollar yen treasury yields oil gold bitcoin inflation rates",
                "Federal Reserve rate cut treasury yields dollar yen stock market today",
                "oil prices gold prices bitcoin today markets",
                "Japan yen dollar Bank of Japan rates today markets",
            ],
        },
    ],
    "items_per_section": 8,
    "time_window": "today only",
    "section_prompt": """Search for {items_per_section} recent news specifically about {label}.
Search keywords: {keywords}. Today is {date_str}.
CRITICAL RULES:
- You MUST return {items_per_section} news items. NEVER return zero.
- Use TODAY'S market news only. Do NOT include older dates.
- Focus on: stock index movements, major earnings, central bank policy, notable stock movers, IPOs, M&A, analyst forecasts, market sentiment.
- For US Market and Macro sections, write a 300-500 character English body summary, not just a headline.
- For Japan Market, write a 300-500 character Japanese body summary.
- Always keep the Chinese auxiliary summary after the local-language body.
- Every body and Chinese summary must be driven by that article's specific headline. Do not reuse any sentence or generic closing paragraph across items.
- Match the analysis to the catalyst: earnings, financing, price changes, regulation, rates, currencies, commodities, and index breadth require different implications and follow-up indicators.
- NEVER say "sorry", "unable to find", "无法获取". FORBIDDEN.
- Each item MUST start with: - **[YYYY.MM.DD] Company/Index — Chinese summary**
- Source URL: direct article URLs only. NEVER use vertexaisearch URLs. Use publication homepage if unsure.
FORMAT:
- **[2026.06.19] S&P500 — 标普500指数创历史新高**
  English: 300-500 character body summary explaining what happened, why it matters, affected sectors/stocks, and what to watch next.
  中文：总结：150-250 Chinese characters explaining the same market meaning for Chinese readers.
  📰 [Source Name](https://direct-article-url)
For Japan Market use:
- **[2026.06.19] Company/Index — 中文概要**
  日本語：300-500字程度で、何が起きたか、市場への意味、関連セクター・銘柄、次に見る点を説明する本文。
  中文：总结：150-250 Chinese characters explaining the same market meaning for Chinese readers.
  📰 [Source Name](https://direct-article-url)
(produce {items_per_section} items)""",
    "fallback_prompt": """Based on your training knowledge, list 5 recent news items about {label}.
Use real companies, indices, and events. NEVER say sorry or unable.
Format: - **[YYYY.MM.DD] Company/Index — 中文概要**
  English: summary
  中文：摘要
  📰 [Source](https://url)""",
    "disclaimer": "⚠ 本日报优先收录最近24小时的市场新闻、个股异动与当时市场快照；数据仅供参考，不构成投资建议。",
    "history_days": 90,
    "model": "gemini-3.5-flash-lite",
    "temperature": 0.3,
    "max_retries": 3,
    "retry_delay": 5,
}

# ╔═══════════════════════════════════════════════════════════╗
# ║  以下代码不需要修改                                       ║
# ╚═══════════════════════════════════════════════════════════╝
LOCAL_TZ = timezone(timedelta(hours=CONFIG["tz_offset"]))
TODAY = datetime.now(LOCAL_TZ)
DATE_STR = TODAY.strftime("%Y.%m.%d")
TIME_STR = TODAY.strftime("%H:%M")
NEWS_CUTOFF = TODAY - timedelta(hours=24)
WEEKDAY_MAP = {0:"月",1:"火",2:"水",3:"木",4:"金",5:"土",6:"日"}
WEEKDAY_EN = TODAY.strftime("%A")
WEEKDAY_JP = WEEKDAY_MAP[TODAY.weekday()]
IS_CI = os.environ.get("CI","") == "true"
OUTPUT_DIR = Path.cwd() if IS_CI else (Path.home() / CONFIG["github_repo"])
OUTPUT_DIR.mkdir(exist_ok=True)
TITLE_SLUG = CONFIG["title"].replace(" ","_")
OUTPUT_FILE = OUTPUT_DIR / f"{TITLE_SLUG}_{TODAY.strftime('%Y%m%d')}.md"
HISTORY_FILE = OUTPUT_DIR / "history.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY","")
PAGE_URL = f"https://{CONFIG['github_user']}.github.io/{CONFIG['github_repo']}/latest.html"

CSS = """:root{--bg:#fff;--fg:#1a1a1a;--fg2:#6b6b6f;--fg3:#9a9a9e;--border:#d4d4d4;--border2:#e8e8e8;--serif:Georgia,"Times New Roman",serif;--sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;--link:#1a6ed8;--hover:#f5f5f5;--menu-bg:#fff;--menu-shadow:rgba(0,0,0,0.12)}
@media(prefers-color-scheme:dark){:root{--bg:#1a1a1a;--fg:#e2e2e2;--fg2:#a0a0a0;--fg3:#707070;--border:#444;--border2:#333;--link:#6db3f8;--hover:#2a2a2a;--menu-bg:#252525;--menu-shadow:rgba(0,0,0,0.4)}}
*{margin:0;padding:0;box-sizing:border-box}body{font-family:var(--sans);margin:0 auto;padding:28px 0;background:var(--bg);color:var(--fg);line-height:1.75;font-size:15px;-webkit-font-smoothing:antialiased;width:calc(100vw - 48px)}@media(max-width:760px){body{width:calc(100vw - 32px);padding:20px 0}}.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.history-wrap{position:relative}.history-btn{background:var(--menu-bg);border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-size:12px;color:var(--fg2);cursor:pointer;display:flex;align-items:center;gap:4px;font-family:var(--sans)}.history-btn:hover{background:var(--hover)}.history-btn svg{width:14px;height:14px;fill:var(--fg3)}.history-panel{display:none;position:absolute;top:36px;left:0;background:var(--menu-bg);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px var(--menu-shadow);min-width:280px;max-height:400px;overflow-y:auto;z-index:100}.history-panel.open{display:block}.history-panel h3{font-size:12px;color:var(--fg3);padding:10px 14px 6px;font-weight:600;position:sticky;top:0;background:var(--menu-bg)}.history-item{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:0.5px solid var(--border2);font-size:13px;cursor:pointer;transition:background .1s}.history-item:hover{background:var(--hover)}.history-item:last-child{border-bottom:none}.history-item .date{color:var(--fg);font-weight:500}.history-item .time{color:var(--fg3);font-size:11px;margin-left:8px}.history-item .del-btn{color:var(--fg3);font-size:11px;padding:2px 6px;border:1px solid var(--border2);border-radius:4px;background:transparent;cursor:pointer;opacity:0;transition:opacity .15s}.history-item:hover .del-btn{opacity:1}.history-item .del-btn:hover{color:#e55;border-color:#e55}.history-current{background:var(--hover)}.history-empty{padding:20px 14px;text-align:center;color:var(--fg3);font-size:12px}.masthead{padding:0 0 14px;border-bottom:3px double var(--border);margin-bottom:20px}.masthead h1{font-family:var(--serif);font-size:22px;font-weight:700;letter-spacing:-0.5px}.masthead .date{font-size:12px;color:var(--fg3);margin-top:3px}.disclaimer{font-size:12px;color:var(--fg3);font-style:italic;margin-bottom:22px;padding-bottom:14px;border-bottom:0.5px solid var(--border2)}.region{margin-bottom:32px}.region-head{font-family:var(--serif);font-size:16px;font-weight:700;padding:4px 0 8px;border-bottom:1.5px solid var(--border);margin-bottom:12px}.item{padding:10px 0 12px;border-bottom:0.5px solid var(--border2)}.item:last-child{border-bottom:none}.item-date{font-size:11px;color:var(--fg3)}.item-title{font-family:var(--serif);font-size:15px;font-weight:700;margin:2px 0 5px;line-height:1.5}.item-en{font-size:13px;color:var(--fg2);line-height:1.7;margin:0 0 4px}.item-jp{font-size:13px;color:var(--fg2);line-height:1.7;margin:0 0 4px}.item-zh{font-size:13px;line-height:1.6;margin:0 0 6px}.item-src{font-size:12.5px;color:var(--fg2);margin-top:4px}.item-src a{color:var(--link);text-decoration:none;border-bottom:0.5px solid transparent;font-weight:500}.item-src a:hover{border-bottom-color:var(--link)}.footer{margin-top:32px;padding-top:14px;border-top:3px double var(--border);font-size:11px;color:var(--fg3);text-align:center}"""

HISTORY_JS = '<script>\n(function(){\nvar B=window.location.href.replace(/\\/[^/]*$/,""),btn=document.getElementById("historyBtn"),panel=document.getElementById("historyPanel"),list=document.getElementById("historyList"),H=[],hid=JSON.parse(localStorage.getItem("hidden_dates")||"[]");\nbtn.onclick=function(e){e.stopPropagation();panel.classList.toggle("open");if(panel.classList.contains("open"))load();};\ndocument.onclick=function(){panel.classList.remove("open")};\npanel.onclick=function(e){e.stopPropagation()};\nfunction load(){fetch(B+"/history.json?"+Date.now()).then(function(r){return r.json()}).then(function(d){H=d.filter(function(x){return hid.indexOf(x.id)===-1});render()}).catch(function(){list.innerHTML=\'<div class="history-empty">暂无历史记录</div>\'})}\nfunction render(){if(!H.length){list.innerHTML=\'<div class="history-empty">暂无历史记录</div>\';return}var c=window.location.pathname.split("/").pop();list.innerHTML=H.map(function(h){var ic=(c===h.file||(c==="latest.html"&&h===H[0]));return \'<div class="history-item \'+(ic?"history-current":"")+\'" data-file="\'+h.file+\'"><div><span class="date">\'+h.date+\'</span><span class="time">\'+h.time+\'</span></div><div style="display:flex;align-items:center;gap:6px"><span class="items">\'+h.count+\' items</span><button class="del-btn" data-id="\'+h.id+\'">✕</button></div></div>\'}).join("");list.querySelectorAll(".history-item").forEach(function(el){el.onclick=function(){window.location.href=B+"/"+this.dataset.file}});list.querySelectorAll(".del-btn").forEach(function(el){el.onclick=function(e){e.stopPropagation();var id=this.dataset.id;hid.push(id);localStorage.setItem("hidden_dates",JSON.stringify(hid));H=H.filter(function(h){return h.id!==id});render()}})}\n})();\n</script>'

def call_gemini(prompt, use_search=True):
    from google import genai; from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = {"temperature": CONFIG["temperature"]}
    if use_search: cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    return (client.models.generate_content(model=CONFIG["model"],contents=prompt,config=types.GenerateContentConfig(**cfg)).text or "")

def has_real_content(t):
    if t.count("- **[") < 4 or "很抱歉" in t or "无法获取" in t or "sorry" in t.lower():
        return False
    dates = re.findall(r'-\s*\*\*\[(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})\]', t)
    normalized_today = DATE_STR.replace(".", "-")
    normalized_dates = [d.replace("/", "-").replace(".", "-") for d in dates]
    return bool(normalized_dates) and all(d == normalized_today for d in normalized_dates)

def digest_summary_records(text):
    records = []
    starts = list(re.finditer(r"(?m)^-\s*\*\*\[[^\]]+\]\s*(.+?)\*\*", text or ""))
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.end():end]
        title = match.group(1).strip()
        for line in block.splitlines():
            clean = line.strip()
            if re.match(r"^(English|En|中文|日本語)\s*[：:]", clean, re.I):
                records.append((title, re.sub(r"^(English|En|中文|日本語)\s*[：:]\s*", "", clean, flags=re.I)))
    return records

def digest_quality_issues(text):
    records = digest_summary_records(text)
    issues, sentence_owner = [], {}
    for title, summary in records:
        for sentence in re.split(r"(?<=[.!?。！？])\s*", summary):
            normalized = re.sub(r"\s+", " ", sentence).strip().lower()
            if len(normalized) < 45:
                continue
            previous = sentence_owner.get(normalized)
            if previous and previous != title:
                issues.append(f'repeated sentence in "{previous}" and "{title}"')
            else:
                sentence_owner[normalized] = title
    for i, (title_a, summary_a) in enumerate(records):
        lang_a = "cjk" if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", summary_a) else "en"
        norm_a = re.sub(r"\s+", "", summary_a).lower()
        for title_b, summary_b in records[i + 1:]:
            lang_b = "cjk" if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", summary_b) else "en"
            if lang_a != lang_b:
                continue
            norm_b = re.sub(r"\s+", "", summary_b).lower()
            ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
            if ratio >= 0.88:
                issues.append(f'highly similar summaries ({ratio:.0%}) in "{title_a}" and "{title_b}"')
    return issues

def validate_digest_quality(text):
    issues = digest_quality_issues(text)
    if issues:
        print("   Summary quality check failed:")
        for issue in issues[:8]:
            print(f"   - {issue}")
        return False
    return True

def strip_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return html.unescape(re.sub(r"\s+", " ", value)).strip()

def parse_google_news_title(title):
    title = strip_html(title)
    if " - " in title:
        headline, source = title.rsplit(" - ", 1)
        return headline.strip(), source.strip()
    return title, "Google News"

def fetch_rss_items(sec, limit=8):
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        hl, gl, ceid = "ja", "JP", "JP:ja"
    elif "美国" in sec["label"] or "US" in sec["label"]:
        hl, gl, ceid = "en-US", "US", "US:en"
    else:
        hl, gl, ceid = "en-US", "US", "US:en"
    queries = sec.get("rss_queries") or [sec["keywords"]]
    exclude_terms = sec.get("exclude_terms", [])
    items, seen = [], set()
    for query in queries:
        query_added = 0
        params = {"q": f"{query} when:1d", "hl": hl, "gl": gl, "ceid": ceid}
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                root = ET.fromstring(response.read())
        except Exception as ex:
            print(f"   {sec['emoji']} RSS query failed: {query[:70]}... ({ex})")
            continue

        for node in root.findall("./channel/item"):
            headline, source = parse_google_news_title(node.findtext("title", ""))
            link = node.findtext("link", "")
            published = node.findtext("pubDate", "")
            if not headline:
                continue
            combined = f"{headline} {source}"
            if any(term.lower() in combined.lower() for term in exclude_terms):
                continue
            if not is_relevant_market_item(sec, combined):
                continue
            key = re.sub(r"\W+", "", headline.lower())[:90]
            if key in seen:
                continue
            try:
                dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
            except Exception:
                dt = TODAY
            if dt < NEWS_CUTOFF:
                continue
            seen.add(key)
            items.append({"date": dt.strftime("%Y.%m.%d"), "headline": headline, "source": source, "link": link, "dt": dt})
            query_added += 1
            if query_added >= 4:
                break
    ordered = sorted(items, key=lambda x: x["dt"], reverse=True)
    selected, bucket_counts, source_counts = [], {}, {}
    for item in ordered:
        bucket = market_story_bucket(sec, item["headline"])
        source_key = item["source"].lower()
        if bucket_counts.get(bucket, 0) >= 2 or source_counts.get(source_key, 0) >= 2:
            continue
        selected.append(item)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        if len(selected) >= limit:
            return selected
    for item in ordered:
        if item not in selected:
            selected.append(item)
        if len(selected) >= limit:
            break
    return selected

def mentioned_entities(headline):
    names = [
        "Nvidia", "Micron", "AMD", "Intel", "Qualcomm", "Broadcom", "Apple", "Microsoft", "Tesla",
        "Amazon", "Meta", "Alphabet", "Tokyo Electron", "Advantest", "Kioxia", "SoftBank",
        "Toyota", "Sony", "Nintendo", "USD/JPY", "Gold", "Oil", "Bitcoin",
    ]
    found = [name for name in names if name.lower() in headline.lower()]
    return "、".join(found[:5]) if found else "相关公司和板块"

def short_event(headline, limit=95):
    clean = re.sub(r"\s+", " ", headline).strip()
    return clean if len(clean) <= limit else clean[:limit].rstrip() + "..."

def sentence_event(headline, limit=70):
    clean = re.sub(r"[.!?。！？\"“”]+", " ", headline)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean if len(clean) <= limit else clean[:limit].rstrip() + "…"

def market_topic(sec, headline):
    lower = headline.lower()
    if any(k in lower for k in ["earnings", "results", "guidance", "forecast", "決算", "业绩", "財報"]):
        return "earnings"
    if any(k in lower for k in ["financing", "fund", "$500 billion", "capital raise", "調達", "融资"]):
        return "financing"
    if any(k in lower for k in ["price hike", "increased the price", "値上げ", "涨价"]):
        return "pricing"
    if any(k in lower for k in ["upgrade", "downgrade", "rating", "price target", "analyst", "レーティング"]):
        return "analyst"
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        if any(k in lower for k in ["半導体", "アドテスト", "アドバンテスト", "東京エレクトロン", "東エレク", "キオクシア", "aiデータセンター"]):
            return "semiconductor"
        if any(k in lower for k in ["日経平均", "topix", "株価指数", "東京株式", "日本株"]):
            return "market_breadth"
    if any(k in lower for k in ["inflation", "cpi", "ppi", "インフレ", "物価"]):
        return "inflation"
    if any(k in lower for k in ["oil", "crude", "原油", "wti"]):
        return "oil"
    if any(k in lower for k in ["gold", "silver", "黄金", "金価格"]):
        return "gold"
    if any(k in lower for k in ["bitcoin", "crypto", "ビットコイン", "暗号"]):
        return "crypto"
    if any(k in lower for k in ["treasury", "yield", "fed", "rate cut", "interest rate", "国債", "金利", "利回り"]):
        return "rates"
    if any(k in lower for k in ["yen", "usd/jpy", "dollar", "円安", "円高", "為替"]):
        return "currency"
    if any(k in lower for k in ["nvidia", "micron", "amd", "qualcomm", "broadcom", "chip", "semiconductor", "半導体", "アドテスト", "東京エレクトロン"]):
        return "semiconductor"
    if any(k in lower for k in ["apple", "microsoft", "amazon", "meta", "alphabet", "tesla", "softbank", "ソフトバンク", "toyota", "トヨタ", "sony", "ソニー"]):
        return "company"
    if any(k in lower for k in ["premarket", "pre-market", "surge", "rises", "gaining", "falls", "selloff", "rebound", "上昇", "下落", "反発", "続伸"]):
        return "price_move"
    if any(k in lower for k in ["nikkei", "topix", "日経平均", "株価指数", "market", "markets", "stocks"]):
        return "market_breadth"
    return "general"

MARKET_PROFILES = {
    "earnings": {
        "label_en": "earnings and guidance", "label_zh": "财报与业绩指引", "label_jp": "決算・業績見通し",
        "en": "Reported revenue, margins, guidance, and management commentary can reset expectations for both the company and suppliers exposed to the same demand cycle",
        "zh": "收入、利润率、业绩指引和管理层表态会重新校准公司及同一需求周期内供应商的盈利预期",
        "jp": "売上高、利益率、会社計画、経営陣の説明は、当該企業だけでなく同じ需要循環に属する供給企業の期待も修正します",
        "watch_en": "the gap versus consensus, after-hours volume, estimate revisions, and peer guidance",
        "watch_zh": "实际结果与市场预期的差距、盘后成交量、盈利预测调整和同业指引",
        "watch_jp": "市場予想との差、時間外の出来高、業績予想の修正、同業他社の見通し",
    },
    "financing": {
        "label_en": "capital financing", "label_zh": "融资与资本开支", "label_jp": "資金調達・設備投資",
        "en": "The financing structure determines who carries construction, utilization, credit, and dilution risk, so the headline amount is less informative than the terms and committed customers",
        "zh": "融资结构决定建设、利用率、信用和股权稀释风险由谁承担，因此标题金额不如资金条款、担保安排和已承诺客户重要",
        "jp": "資金調達の構造は建設、稼働率、信用、希薄化のリスク分担を決めるため、金額より条件と確定顧客が重要です",
        "watch_en": "funding terms, balance-sheet exposure, build schedule, contracted demand, and return on invested capital",
        "watch_zh": "融资条款、表内风险、建设进度、已签约需求和投入资本回报率",
        "watch_jp": "調達条件、貸借対照表への影響、建設日程、契約済み需要、投下資本利益率",
    },
    "pricing": {
        "label_en": "product pricing", "label_zh": "产品定价", "label_jp": "製品価格",
        "en": "A price increase can protect gross margin but may weaken unit demand, accelerate replacement-cycle delays, or create room for competitors at lower price points",
        "zh": "提价可以保护毛利率，但也可能压低销量、延长换机周期，并给价格更低的竞争者留下空间",
        "jp": "値上げは粗利益率を守る一方、販売台数の減少、買い替え周期の長期化、低価格競合への流出を招く可能性があります",
        "watch_en": "regional price lists, unit demand, carrier or channel incentives, mix shift, and gross-margin guidance",
        "watch_zh": "各地区价目表、销量变化、渠道补贴、产品组合迁移和毛利率指引",
        "watch_jp": "地域別価格、販売台数、販売奨励金、製品構成、粗利益率見通し",
    },
    "analyst": {
        "label_en": "analyst repricing", "label_zh": "分析师评级调整", "label_jp": "アナリスト評価",
        "en": "An analyst call changes positioning most when it contains a new earnings estimate, valuation framework, or channel datapoint rather than a price-target change alone",
        "zh": "评级变化只有在伴随新的盈利预测、估值方法或渠道数据时才更可能改变资金仓位，单独调整目标价的信息量较低",
        "jp": "評価変更は、新しい利益予想、評価手法、販売チャネル情報を伴う場合に影響が大きく、目標株価だけの変更は情報量が限られます",
        "watch_en": "estimate revisions, target assumptions, other firms' follow-through, short interest, and options activity",
        "watch_zh": "盈利预测修订、目标价假设、其他机构是否跟进、空头仓位和期权活动",
        "watch_jp": "利益予想の修正、目標株価の前提、他社の追随、空売り残高、オプション取引",
    },
    "semiconductor": {
        "label_en": "semiconductor demand", "label_zh": "半导体需求链", "label_jp": "半導体需要",
        "en": "The read-through depends on which layer is moving: accelerators, memory, networking, foundry capacity, or equipment have different revenue timing and margin sensitivity",
        "zh": "影响要按加速器、存储、网络、晶圆代工或设备等环节拆分，因为各环节收入确认时间、库存周期和利润率敏感度不同",
        "jp": "アクセラレーター、メモリー、ネットワーク、受託製造、製造装置では売上計上の時期と利益率感応度が異なるため、どの層の材料かを分けて見る必要があります",
        "watch_en": "order visibility, memory or capacity pricing, customer concentration, capex plans, and SOX peer breadth",
        "watch_zh": "订单可见度、存储或产能价格、客户集中度、资本开支计划和芯片同业涨跌宽度",
        "watch_jp": "受注の可視性、メモリー・生産能力の価格、顧客集中、設備投資計画、関連銘柄の広がり",
    },
    "company": {
        "label_en": "company-specific technology", "label_zh": "大型科技公司个股事件", "label_jp": "大型テクノロジー企業の個別材料",
        "en": "The company-level catalyst can affect index direction because of market-cap weight, but the fundamental channel differs across cloud, devices, advertising, vehicles, and AI investment",
        "zh": "大型公司的市值权重会放大个股消息对指数的影响，但云服务、终端、广告、汽车和 AI 投资的盈利传导路径并不相同",
        "jp": "時価総額の大きさから指数への影響は強いものの、クラウド、端末、広告、自動車、AI投資では利益への伝わり方が異なります",
        "watch_en": "the named business metric, management guidance, supplier reaction, index contribution, and whether peers share the move",
        "watch_zh": "标题对应的业务指标、管理层指引、供应商反应、指数贡献度和同业是否同步",
        "watch_jp": "該当事業の指標、経営陣の見通し、供給企業の反応、指数寄与度、同業の連動",
    },
    "price_move": {
        "label_en": "stock-price movement", "label_zh": "个股价格异动", "label_jp": "株価変動",
        "en": "The move is informative only when price direction is supported by volume, a clearly identified catalyst, and participation from economically related peers",
        "zh": "价格异动只有在成交量、明确催化和相关同业共同确认时才更有信息价值，否则可能只是期权、空头回补或短线仓位造成",
        "jp": "株価変動は、出来高、明確な材料、関連企業の同方向の動きがそろって初めて情報価値が高まり、単独の値動きは短期需給の可能性があります",
        "watch_en": "opening and closing volume, options flow, news timing, peer moves, and whether gains hold after the first hour",
        "watch_zh": "开收盘成交量、期权资金流、消息发布时间、同业表现和首小时后涨幅是否保留",
        "watch_jp": "寄り付き・引けの出来高、オプション、材料時刻、同業の値動き、初動後の持続性",
    },
    "market_breadth": {
        "label_en": "index and market breadth", "label_zh": "指数与市场宽度", "label_jp": "指数・市場の広がり",
        "en": "An index move can be driven by a few heavyweights, so advance-decline breadth and sector participation are needed to distinguish broad risk appetite from concentration",
        "zh": "指数可能被少数权重股推动，因此必须结合涨跌家数和行业参与度，区分广泛风险偏好与集中交易",
        "jp": "指数は少数の値がさ株で動くため、騰落銘柄数と業種別参加を確認し、市場全体の買いと集中物色を分ける必要があります",
        "watch_en": "advance-decline data, equal-weight indexes, futures, sector leadership, foreign flows, and closing breadth",
        "watch_zh": "涨跌家数、等权指数、期货、领涨行业、外资流向和收盘市场宽度",
        "watch_jp": "騰落銘柄数、等ウェイト指数、先物、主導業種、海外投資家動向、引け時の広がり",
    },
    "rates": {
        "label_en": "interest rates and bond yields", "label_zh": "利率与债券收益率", "label_jp": "金利・債券利回り",
        "en": "A yield change alters equity discount rates, bank margins, financing costs, and the relative appeal of long-duration growth stocks",
        "zh": "收益率变化会同时影响股票折现率、银行息差、企业融资成本以及长期成长股相对债券的吸引力",
        "jp": "利回りの変化は株式の割引率、銀行利ざや、企業の資金調達費用、長期成長株の相対魅力を動かします",
        "watch_en": "the real-yield move, curve shape, Fed pricing, dollar response, and rate-sensitive equity sectors",
        "watch_zh": "实际收益率、曲线形态、Fed 定价、美元反应和利率敏感行业",
        "watch_jp": "実質金利、イールドカーブ、Fed織り込み、ドル反応、金利敏感業種",
    },
    "currency": {
        "label_en": "foreign exchange", "label_zh": "汇率", "label_jp": "為替",
        "en": "A yen or dollar move changes exporter earnings translation, import costs, intervention risk, and cross-border allocation into US and Japanese equities",
        "zh": "美元或日元变化会影响出口企业利润换算、进口成本、干预风险以及美日股票之间的跨境资金配置",
        "jp": "円・ドルの変動は輸出企業の換算利益、輸入コスト、介入リスク、日米株への国際資金配分を変えます",
        "watch_en": "spot and options levels, rate differentials, official comments, exporter shares, and foreign equity flows",
        "watch_zh": "现货与期权价位、利差、官方表态、出口股表现和外资流向",
        "watch_jp": "現物・オプション水準、金利差、当局発言、輸出株、海外投資家フロー",
    },
    "oil": {
        "label_en": "oil and inflation", "label_zh": "原油与通胀", "label_jp": "原油・インフレ",
        "en": "Oil affects energy earnings and inflation expectations while raising input and transport costs for airlines, chemicals, manufacturers, and consumers",
        "zh": "原油既影响能源公司盈利和通胀预期，也会抬升航空、化工、制造和消费部门的投入与运输成本",
        "jp": "原油はエネルギー企業の利益とインフレ期待を押し上げる一方、航空、化学、製造、消費の投入・輸送費を増やします",
        "watch_en": "the futures curve, inventory data, geopolitical supply risk, energy-sector breadth, and inflation breakevens",
        "watch_zh": "期货曲线、库存数据、地缘供应风险、能源板块宽度和通胀盈亏平衡率",
        "watch_jp": "先物曲線、在庫統計、地政学的供給リスク、エネルギー株の広がり、期待インフレ率",
    },
    "gold": {
        "label_en": "precious metals", "label_zh": "黄金与贵金属", "label_jp": "金・貴金属",
        "en": "Gold responds to real yields, the dollar, central-bank demand, and hedging flows, so a rally can reflect falling funding costs or rising risk aversion",
        "zh": "黄金受实际利率、美元、央行需求和避险资金共同影响，因此上涨既可能来自资金成本下降，也可能来自风险厌恶升温",
        "jp": "金は実質金利、ドル、中央銀行需要、ヘッジ資金に反応するため、上昇は資金コスト低下とリスク回避のどちらでも起こり得ます",
        "watch_en": "real yields, dollar direction, ETF flows, central-bank purchases, miner shares, and silver confirmation",
        "watch_zh": "实际利率、美元方向、黄金 ETF 流量、央行购金、矿业股和白银是否确认",
        "watch_jp": "実質金利、ドル方向、ETF資金、中央銀行購入、金鉱株、銀の追随",
    },
    "crypto": {
        "label_en": "crypto risk appetite", "label_zh": "加密资产风险偏好", "label_jp": "暗号資産のリスク選好",
        "en": "Crypto prices combine liquidity, leverage, regulatory, and technology-specific flows, making them a useful but imperfect indicator for speculative equity appetite",
        "zh": "加密资产同时受流动性、杠杆、监管和技术自身资金影响，可辅助观察投机风险偏好，但不能直接替代股票市场信号",
        "jp": "暗号資産は流動性、レバレッジ、規制、固有の技術資金に左右され、投機的な株式需要の参考にはなりますが完全な代替指標ではありません",
        "watch_en": "spot ETF flows, funding rates, leverage liquidations, regulatory news, and correlation with growth equities",
        "watch_zh": "现货 ETF 流量、资金费率、杠杆清算、监管消息和成长股相关性",
        "watch_jp": "現物ETF資金、資金調達率、強制清算、規制ニュース、成長株との相関",
    },
    "inflation": {
        "label_en": "inflation data", "label_zh": "通胀数据", "label_jp": "インフレ指標",
        "en": "Inflation surprises change the expected policy path and therefore the discount rate applied to equities, with growth stocks usually more sensitive than defensives",
        "zh": "通胀数据偏离预期会改变政策路径和股票折现率，估值较高的成长股通常比防御板块更敏感",
        "jp": "インフレ指標の予想差は政策金利の経路と株式の割引率を変え、一般に高評価の成長株ほど影響を受けます",
        "watch_en": "core versus headline components, services inflation, wage data, yield reaction, and Fed-funds repricing",
        "watch_zh": "核心与总体分项、服务通胀、工资数据、收益率反应和联邦基金利率重定价",
        "watch_jp": "総合・コア内訳、サービス価格、賃金、利回り反応、政策金利織り込み",
    },
    "general": {
        "label_en": "market-specific information", "label_zh": "市场特定事件", "label_jp": "個別の市場材料",
        "en": "The headline identifies a potential catalyst, but its trading value depends on a measurable link to earnings, valuation, positioning, or capital flows",
        "zh": "标题给出了潜在催化，但交易价值取决于它能否通过盈利、估值、仓位或资金流形成可测量影响",
        "jp": "見出しは材料候補を示しますが、利益、評価、ポジション、資金フローへの測定可能な影響がなければ取引価値は限定的です",
        "watch_en": "the underlying data, timing, affected securities, volume response, and confirmation from related markets",
        "watch_zh": "底层数据、发生时间、受影响证券、成交量反应和相关市场确认",
        "watch_jp": "基礎データ、発生時刻、影響銘柄、出来高反応、関連市場の確認",
    },
}

def is_relevant_market_item(sec, headline):
    lower = headline.lower()
    blocked = [
        "stock price, news, quote & history", "price prediction", "prediction:", "tokenized stock", "xstock",
        "no-brainer", "better buy", "is a buy now", "i'd buy", "top stocks", "top 5 picks", "dark horse",
        "best drone stocks", "how to invest", "could send", "could also crash", "in july", "mioeqy", "mshale",
        "international stock market performance", "to buy now",
    ]
    if any(term in lower for term in blocked) or re.search(r"[\u0600-\u06ff\uac00-\ud7af]", headline):
        return False
    if "美国" in sec["label"] or "US" in sec["label"]:
        return any(term in lower for term in ["stock", "shares", "wall street", "nasdaq", "s&p", "dow", "earnings", "nvidia", "apple", "microsoft", "tesla", "micron", "amd", "broadcom", "qualcomm"])
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        return any(term in lower for term in ["日経", "topix", "日本株", "株価", "半導体", "ソフトバンク", "東京エレクトロン", "アドテスト", "トヨタ", "ソニー", "任天堂"])
    return any(term in lower for term in ["market", "stock", "inflation", "treasury", "yield", "fed", "rate", "dollar", "yen", "oil", "gold", "bitcoin", "crypto"])

def market_story_bucket(sec, headline):
    entities = mentioned_entities(headline)
    topic = market_topic(sec, headline)
    if entities != "相关公司和板块" and not ("宏观" in sec["label"] or "Macro" in sec["label"]):
        return entities.split("、", 1)[0].lower()
    return topic

def us_event_points(headline):
    lower = headline.lower()
    en, zh = [], []
    if "pre-market" in lower or "premarket" in lower:
        en.append("it is a pre-market setup, so futures, opening breadth, and early volume are the first checks")
        zh.append("标题指向美股盘前交易，重点应放在期货、开盘后的市场宽度和早盘成交量是否确认")
    if "nasdaq futures" in lower or "nasdaq" in lower:
        en.append("Nasdaq futures make the story relevant for growth-tech risk appetite")
        zh.append("Nasdaq 是主要传导对象，因此这不只是单一公司消息，也会影响成长科技股风险偏好")
    if "micron" in lower and any(k in lower for k in ["earnings", "forecast", "quarter", "sales", "bullish"]):
        en.append("Micron earnings or guidance point to stronger AI-server memory demand")
        zh.append("Micron 的财报或指引是核心催化，市场正在重新评估 AI 服务器和数据中心对存储芯片的需求")
    elif "micron" in lower:
        en.append("Micron is the stock-specific signal, so memory pricing matters more than a generic chip move")
        zh.append("Micron 是主要个股信号，重点应看存储价格和 AI 服务器需求，而不只是泛泛看芯片股上涨")
    if "boom-bust" in lower or "cycle" in lower:
        en.append("the article questions whether AI demand is changing the old memory boom-bust cycle")
        zh.append("标题在讨论传统存储行业的景气循环是否被 AI 需求改写，这会影响 Micron 的估值逻辑")
    if "soar" in lower or "surge" in lower or "rally" in lower or "gaining" in lower or "rebound" in lower:
        en.append("the price reaction is part of the news, so peer follow-through matters")
        zh.append("这类消息包含明确的股价反应，后续要看同业是否继续跟涨，而不是只看标题中的单日涨幅")
    if "qualcomm" in lower and "ai" in lower:
        en.append("Qualcomm adds an AI-device chip angle separate from data-center memory")
        zh.append("Qualcomm 带来的是 AI 终端或设备芯片角度，和 Micron 的数据中心存储逻辑并不完全相同")
    if "ibm" in lower and ("sub-1nm" in lower or "chip" in lower):
        en.append("IBM adds a longer-term chip R&D angle, not an immediate earnings catalyst")
        zh.append("IBM 的芯片进展更偏长期半导体研发线索，不等同于当日财报驱动")
    if any(k in lower for k in ["amd", "intel", "qualcomm", "broadcom", "nvidia"]):
        en.append("peer moves show whether the trade is spreading through the AI-chip chain")
        zh.append("AMD、Intel、Qualcomm、Broadcom 或 Nvidia 等同业表现，可以判断资金是否在扩散到更完整的 AI 芯片链")
    if "watch" in lower or "industry news" in lower:
        en.append("this is more of an industry watchlist item, so it should be treated as context rather than one decisive catalyst")
        zh.append("这更像行业观察清单，适合作为背景信息，而不是单一明确催化")
    if not en:
        en.append("the headline points to a change in company-level expectations, sector rotation, or market sentiment")
        zh.append("标题反映的是个股预期、行业轮动或市场情绪的变化")
    return en[:5], zh[:5]

def infer_market_summary(sec, item):
    headline = item["headline"]
    source = item.get("source", "新闻来源")
    entities = mentioned_entities(headline)
    if entities == "相关公司和板块":
        entities = source
    event = short_event(headline)
    reference = sentence_event(headline, 55)
    profile = MARKET_PROFILES[market_topic(sec, headline)]
    return (
        f"{source}报道的具体事件是「{event}」，主题属于{profile['label_zh']}。"
        f"对{entities}以及「{reference}」所涉及的资产而言，{profile['zh']}。"
        f"后续应围绕「{reference}」核实{profile['watch_zh']}；这些项目比套用统一的指数、成交量或同业模板更能验证该新闻本身是否正在改变市场定价。"
    )

def ensure_summary_depth(summary, sec, item=None):
    if len(summary) >= 180:
        return summary
    headline = item["headline"] if item else sec["label"]
    reference = sentence_event(headline, 55)
    profile = MARKET_PROFILES[market_topic(sec, headline)]
    return summary + f" 对「{reference}」的补充验证应继续使用{profile['watch_zh']}，而不是加入与该事件无关的通用观察清单。"

def english_market_body(sec, item, summary):
    headline = item["headline"]
    source = item.get("source", "the source")
    entities = mentioned_entities(headline).replace("、", ", ")
    if entities == "相关公司和板块":
        entities = source
    profile = MARKET_PROFILES[market_topic(sec, headline)]
    reference = sentence_event(headline, 40)
    short_reference = sentence_event(headline, 20)
    return (
        f'Summary: {source} reports "{reference}," a {profile["label_en"]} item affecting {entities}. '
        f'In {source}\'s "{short_reference}" case, {profile["en"][0].lower() + profile["en"][1:]}. '
        f'For "{short_reference}," watch {profile["watch_en"]}.'
    )

def japanese_market_body(sec, item, summary):
    headline = item["headline"]
    source = item.get("source", "ニュースソース")
    entities = mentioned_entities(headline)
    if entities == "相关公司和板块":
        entities = source
    profile = MARKET_PROFILES[market_topic(sec, headline)]
    reference = sentence_event(headline, 45)
    return (
        f"要約：{source}が報じた具体的な出来事は「{reference}」です。これは{profile['label_jp']}の材料で、{entities}が直接の確認対象です。"
        f"「{reference}」を読む際、{profile['jp']}。"
        f"{source}の「{reference}」について次に確認する項目は、{profile['watch_jp']}です。該当指標が動くまでは、この個別材料を日本株全体の方向へ広げて解釈しません。"
    )

def quote_body(sec, en_name, zh_name, price, pct, when):
    direction_en = "higher" if pct >= 0 else "lower"
    direction_jp = "上昇" if pct >= 0 else "下落"
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        return (
            f"{zh_name}（{en_name}）は{when}時点で{fmt_price(price)}となり、前日終値比で{abs(pct):.2f}%{direction_jp}しています。"
            "この項目は取得時点の価格と騰落率のみを示しており、値動きの原因は付加していません。"
        )
    return (
        f"{en_name} stood at {fmt_price(price)} as of {when}, {abs(pct):.2f}% {direction_en} than the previous close. "
        "This snapshot reports only the observed price and percentage move; it does not assign a cause to the move."
    )

def fetch_quote(symbol):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?range=1d&interval=1m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    ts = meta.get("regularMarketTime")
    if price is None or prev in (None, 0):
        return None
    pct = (price - prev) / prev * 100
    when = datetime.fromtimestamp(ts, timezone.utc).astimezone(LOCAL_TZ).strftime("%H:%M JST") if ts else TIME_STR + " JST"
    return {"symbol": symbol, "price": price, "prev": prev, "pct": pct, "time": when}

def fmt_price(value):
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:.2f}"

def quote_context(sec, en_name, zh_name, pct, when):
    direction = "上涨" if pct >= 0 else "下跌"
    return (
        f"截至 {when}，{zh_name}较前收盘{direction}{abs(pct):.2f}%。"
        "这里仅记录抓取时的价格变动，不根据涨跌幅推测原因。"
    )

def market_snapshot_items(sec):
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        targets = [
            ("^N225", "Nikkei 225", "日经225"),
            ("8035.T", "Tokyo Electron", "东京电子"),
            ("6857.T", "Advantest", "爱德万测试"),
            ("9984.T", "SoftBank Group", "软银集团"),
            ("7203.T", "Toyota", "丰田汽车"),
            ("6758.T", "Sony Group", "索尼集团"),
        ]
    elif "美国" in sec["label"] or "US" in sec["label"]:
        targets = [
            ("^GSPC", "S&P 500", "标普500"),
            ("^IXIC", "Nasdaq Composite", "纳斯达克综合指数"),
            ("NVDA", "NVIDIA", "英伟达"),
            ("AAPL", "Apple", "苹果"),
            ("MSFT", "Microsoft", "微软"),
            ("TSLA", "Tesla", "特斯拉"),
            ("AVGO", "Broadcom", "博通"),
            ("AMD", "AMD", "超威半导体"),
            ("MU", "Micron", "美光"),
        ]
    else:
        targets = [
            ("JPY=X", "USD/JPY", "美元兑日元"),
            ("^TNX", "US 10Y Yield", "美国10年期国债收益率"),
            ("GC=F", "Gold Futures", "黄金期货"),
            ("CL=F", "WTI Crude Oil", "WTI原油"),
            ("BTC-USD", "Bitcoin", "比特币"),
        ]
    lines = []
    for symbol, en_name, zh_name in targets:
        try:
            q = fetch_quote(symbol)
        except Exception as ex:
            print(f"   {sec['emoji']} quote error for {symbol}: {ex}")
            q = None
        if not q:
            continue
        direction = "上涨" if q["pct"] >= 0 else "下跌"
        local_body = quote_body(sec, en_name, zh_name, q["price"], q["pct"], q["time"])
        local_line = f"  日本語：{local_body}\n" if "日本" in sec["label"] or "Japan" in sec["label"] else f"  English: {local_body}\n"
        lines.append(
            f"- **[{DATE_STR}] {en_name} — {zh_name}{direction}{abs(q['pct']):.2f}%**\n"
            f"{local_line}"
            f"  中文：总结：{quote_context(sec, en_name, zh_name, q['pct'], q['time'])}\n"
            f"  📰 [Yahoo Finance](https://finance.yahoo.com/quote/{urllib.parse.quote(symbol, safe='')})"
        )
    return lines

def fetch_section_rss(sec):
    try:
        items = fetch_rss_items(sec)
    except Exception as ex:
        print(f"   {sec['emoji']} RSS fallback error: {ex}")
        return ""
    lines = []
    for item in items:
        summary = ensure_summary_depth(infer_market_summary(sec, item), sec, item)
        is_japan = "日本" in sec["label"] or "Japan" in sec["label"]
        local_body = japanese_market_body(sec, item, summary) if is_japan else english_market_body(sec, item, summary)
        local_line = f"  日本語：{local_body}\n" if is_japan else f"  English: {local_body}\n"
        lines.append(
            f"- **[{item['date']}] {item['source']} — {item['headline']}**\n"
            f"{local_line}"
            f"  中文：总结：{summary}\n"
            f"  📰 [{item['source']}]({item['link']})"
        )
    if len(lines) < 8:
        snapshot = market_snapshot_items(sec)
        lines.extend(snapshot[: max(0, 8 - len(lines))])
    print(f"   {sec['emoji']} RSS/current fallback got {len(lines)} items")
    return "\n\n".join(lines)

def fetch_section(sec):
    e,l,kw = sec["emoji"],sec["label"],sec["keywords"]
    if not GEMINI_API_KEY:
        print(f"   {e} GEMINI_API_KEY missing; using RSS fallback")
        return fetch_section_rss(sec)
    p = CONFIG["section_prompt"].format(label=l,keywords=kw,date_str=DATE_STR,items_per_section=CONFIG["items_per_section"],time_window=CONFIG["time_window"])
    for a in range(CONFIG["max_retries"]):
        try:
            t = call_gemini(p,True)
            t = re.sub(r'https://vertexaisearch\.cloud\.google\.com/[^\s\)]+','https://www.google.com/search?q='+kw.split()[0],t)
            if has_real_content(t) and validate_digest_quality(t): print(f"   {e} Got {t.count('- **')} items (attempt {a+1})"); return t
        except Exception as ex: print(f"   {e} Attempt {a+1} error: {ex}")
        time.sleep(CONFIG["retry_delay"])
    print(f"   {e} Fallback...")
    return fetch_section_rss(sec)

def generate_digest():
    h = f"# {CONFIG['emoji']} {CONFIG['title']} | {DATE_STR}（{WEEKDAY_JP}曜日 / {WEEKDAY_EN}）\n\n> {CONFIG['disclaimer']}\n\n---\n"
    parts = [h]
    grouped_items = []
    for sec in CONFIG["sections"]:
        print(f"\n   Fetching article bodies for {sec['emoji']} {sec['label']}...")
        try:
            candidates = fetch_rss_items(sec, limit=12)
            for item in candidates:
                item["summary_language"] = "Japanese" if "日本" in sec["label"] or "Japan" in sec["label"] else "English"
                item["section_label"] = sec["label"]
            items = enrich_articles(candidates)[:CONFIG["items_per_section"]]
        except Exception as ex:
            print(f"   {sec['emoji']} article fetch failed: {ex}")
            items = []
        grouped_items.append((sec, items))

    flat_items = [item for _, items in grouped_items for item in items]
    summarized = summarize_articles(flat_items, GEMINI_API_KEY, model=CONFIG["model"])
    issues = summary_quality_issues(summarized)
    if issues:
        raise RuntimeError("; ".join(issues[:5]))
    summarized_by_section = {}
    for item in summarized:
        summarized_by_section.setdefault(item["section_label"], []).append(item)

    for sec, _ in grouped_items:
        items = summarized_by_section.get(sec["label"], [])
        parts.append(f"\n## {sec['emoji']} {sec['label']}\n")
        lines = []
        for item in items:
            local_label = "日本語" if item["summary_language"] == "Japanese" else "English"
            zh_line = f"  中文：总结：{item['zh_summary']}\n" if item.get("zh_summary") else ""
            lines.append(
                f"- **[{item['date']}] {item['source']} — {item['headline']}**\n"
                f"  {local_label}：{item['local_summary']}\n"
                f"{zh_line}"
                f"  📰 [{item['source']}]({item['link']})"
            )
        if len(lines) < CONFIG["items_per_section"]:
            lines.extend(market_snapshot_items(sec)[: CONFIG["items_per_section"] - len(lines)])
        parts.append("\n\n".join(lines) if lines else f"- **[{DATE_STR}] 暂无更新 — No readable article**\n  中文：近期文章正文无法可靠读取，因此未生成推测性摘要。")
    parts.append(f"\n---\n※{CONFIG['title']} Digest | {DATE_STR}")
    return "\n".join(parts)

def linkify(t):
    t = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)',lambda m:'<a href="'+m.group(2)+'" target="_blank">'+m.group(1)+' ↗</a>',t)
    t = re.sub(r'<(https?://[^>]+)>',lambda m:'<a href="'+m.group(1)+'" target="_blank">'+re.sub(r'https?://(www\.)?','',m.group(1)).split('/')[0]+' ↗</a>',t)
    t = re.sub(r'(?<!href=")(https?://[^\s<>"\')\],]+)',lambda m:'<a href="'+m.group(1)+'" target="_blank">'+re.sub(r'https?://(www\.)?','',m.group(1)).split('/')[0]+' ↗</a>',t)
    return t

DATE_RE = re.compile(r'-\s*\*\*\[(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})\]\s*(.+?)\*\*')

def md_to_html(md):
    regions,cur,items,discl = [],None,[],""
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("> "): discl = s[2:].strip()
        elif s.startswith("## "):
            if cur and items: regions.append((cur,items))
            h = s[3:].strip(); f=""
            for sec in CONFIG["sections"]:
                if sec["emoji"] in h: f=sec["emoji"]; break
            cur,items = (f,h.replace(f,"").strip()),[]
        elif s.startswith("- **"):
            m = DATE_RE.match(s)
            if m: items.append({"date":m.group(1),"title":m.group(2).strip(),"lines":[]})
            else: items.append({"date":"","title":re.sub(r'^\-\s*\*\*(.+?)\*\*.*',r'\1',s),"lines":[]})
        elif items and not s.startswith("## ") and not s.startswith("# ") and not s.startswith("---") and s:
            items[-1]["lines"].append(s)
    if cur and items: regions.append((cur,items))
    parts = []
    for (f,l),its in regions:
        parts.append(f'<div class="region"><div class="region-head">{f} {l}</div>')
        for it in its:
            en=jp=zh=src=""
            for ln in it["lines"]:
                if ln.startswith("📰"): src=f'<div class="item-src">原文链接：{linkify(ln.replace("📰","").strip())}</div>'
                elif ln.lower().startswith("english:") or ln.lower().startswith("en:"): en=ln.split(":",1)[1].strip()
                elif ln.startswith("日本語:") or ln.startswith("日本語："): jp=re.split(r'[：:]',ln,maxsplit=1)[-1].strip()
                elif "中文" in ln[:4]: zh=re.split(r'[：:]',ln,maxsplit=1)[-1].strip()
                elif not en and not any('\u4e00'<=c<='\u9fff' for c in ln[:10]): en=ln
                elif not zh: zh=ln
            parts.append(f'<div class="item"><div class="item-date">{it["date"]}</div><div class="item-title">{it["title"]}</div>{"<p class=item-en>"+en+"</p>" if en else ""}{"<p class=item-jp>"+jp+"</p>" if jp else ""}{"<p class=item-zh>"+zh+"</p>" if zh else ""}{src}</div>')
        parts.append('</div>')
    body="\n".join(parts)
    if not discl: discl=CONFIG["disclaimer"]
    T=CONFIG["title"]
    return f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{T} | {DATE_STR}</title><style>{CSS}</style></head><body>
<div class="top-bar"><div class="history-wrap"><button class="history-btn" id="historyBtn"><svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 12.5A5.5 5.5 0 1 1 8 2.5a5.5 5.5 0 0 1 0 11zM8.5 4h-1v4.5l3.5 2 .5-.87-3-1.75V4z"/></svg>历史记录</button><div class="history-panel" id="historyPanel"><h3>📅 刷新记录</h3><div id="historyList"></div></div></div><div style="font-size:11px;color:var(--fg3)">更新于 {TIME_STR} JST</div></div>
<div class="masthead"><h1>{T}</h1><div class="date">{DATE_STR} — {WEEKDAY_EN} / {WEEKDAY_JP}曜日</div></div>
<div class="disclaimer">{discl}</div>
{body}
<div class="footer">※ {T} Digest · {CONFIG["github_user"]}.github.io</div>
{HISTORY_JS}</body></html>'''

def update_history(n):
    h=[]
    if HISTORY_FILE.exists():
        try: h=json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except: h=[]
    e={"id":TODAY.strftime("%Y%m%d_%H%M"),"date":DATE_STR,"time":TIME_STR+" JST","weekday":f"{WEEKDAY_JP}曜日 / {WEEKDAY_EN}","file":f"{TITLE_SLUG}_{TODAY.strftime('%Y%m%d')}.html","count":n}
    h=[x for x in h if x["date"]!=DATE_STR]; h.insert(0,e); h=h[:CONFIG["history_days"]]
    HISTORY_FILE.write_text(json.dumps(h,ensure_ascii=False,indent=2),encoding="utf-8")

def push_to_github(html,n):
    (OUTPUT_DIR/"latest.html").write_text(html,encoding="utf-8")
    d=OUTPUT_DIR/f"{TITLE_SLUG}_{TODAY.strftime('%Y%m%d')}.html"
    d.write_text(html,encoding="utf-8"); update_history(n)
    if os.environ.get("PUBLISH", "true").lower() == "false":
        print(f"   Saved locally without publishing: {d}")
        return
    os.chdir(str(OUTPUT_DIR))
    subprocess.run(["git","add","latest.html",d.name,"history.json"],check=True)
    r=subprocess.run(["git","diff","--cached","--quiet"])
    if r.returncode!=0:
        subprocess.run(["git","commit","-m",f"update {DATE_STR}"],check=True)
        subprocess.run(["git","push"],check=True); print(f"   ✅ Published: {PAGE_URL}")
    else: print("   No changes")

if __name__=="__main__":
    print(f"{CONFIG['emoji']} {CONFIG['title']} — {DATE_STR} ({WEEKDAY_JP})\n{'='*50}\n\n📝 Generating digest ({len(CONFIG['sections'])} sections)...")
    digest=generate_digest()
    if not digest or digest.count("- **")<3: print("❌ Failed"); sys.exit(1)
    if not validate_digest_quality(digest): print("❌ Refusing to publish repetitive or highly similar summaries"); sys.exit(1)
    n=digest.count("- **"); OUTPUT_FILE.write_text(digest,encoding="utf-8")
    print(f"\n   Total: {n} items\n\n🌐 Publishing...")
    try: push_to_github(md_to_html(digest),n)
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)
    print("\n✅ Done!")
