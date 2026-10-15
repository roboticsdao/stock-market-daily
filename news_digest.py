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
from edition_health import publisher_candidates, write_feed

from article_summaries import deduplicate_summaries, enrich_articles, fetch_rss_bytes, remove_repeated_summary_sentences, summarize_articles, summary_quality_issues

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
                "(日経平均 OR TOPIX OR 日本株) 株式",
                "(決算 OR 業績 OR レーティング) 日本株",
                "(東京エレクトロン OR アドバンテスト OR ソフトバンク) 株",
                "(トヨタ OR ソニー OR 任天堂) (決算 OR 株価 OR 業績)",
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

CSS = """:root{color-scheme:light;--bg:#fff;--fg:#1a1a1a;--fg2:#6b6b6f;--fg3:#9a9a9e;--border:#d4d4d4;--border2:#e8e8e8;--serif:Georgia,"Times New Roman",serif;--sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;--link:#1a6ed8;--hover:#f5f5f5;--menu-bg:#fff;--menu-shadow:rgba(0,0,0,0.12)}
:root[data-theme="dark"]{color-scheme:dark;--bg:#1a1a1a;--fg:#e2e2e2;--fg2:#a0a0a0;--fg3:#707070;--border:#444;--border2:#333;--link:#6db3f8;--hover:#2a2a2a;--menu-bg:#252525;--menu-shadow:rgba(0,0,0,0.4)}
@media(prefers-color-scheme:dark){:root:not([data-theme]){color-scheme:dark;--bg:#1a1a1a;--fg:#e2e2e2;--fg2:#a0a0a0;--fg3:#707070;--border:#444;--border2:#333;--link:#6db3f8;--hover:#2a2a2a;--menu-bg:#252525;--menu-shadow:rgba(0,0,0,0.4)}}
*{margin:0;padding:0;box-sizing:border-box}body{font-family:var(--sans);margin:0 auto;padding:28px 0;background:var(--bg);color:var(--fg);line-height:1.75;font-size:15px;-webkit-font-smoothing:antialiased;width:calc(100vw - 48px)}@media(max-width:760px){body{width:calc(100vw - 32px);padding:20px 0}}.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.top-actions{display:flex;align-items:center;gap:10px}.updated-at{font-size:11px;color:var(--fg3);white-space:nowrap}.theme-btn{width:32px;height:32px;display:grid;place-items:center;border:1px solid var(--border);border-radius:8px;background:var(--menu-bg);color:var(--fg2);font:18px/1 var(--sans);cursor:pointer}.theme-btn:hover{background:var(--hover);color:var(--fg)}.theme-btn:focus-visible{outline:2px solid var(--link);outline-offset:2px}.history-wrap{position:relative}.history-btn{background:var(--menu-bg);border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-size:12px;color:var(--fg2);cursor:pointer;display:flex;align-items:center;gap:4px;font-family:var(--sans)}.history-btn:hover{background:var(--hover)}.history-btn svg{width:14px;height:14px;fill:var(--fg3)}.history-panel{display:none;position:absolute;top:36px;left:0;background:var(--menu-bg);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px var(--menu-shadow);min-width:280px;max-height:400px;overflow-y:auto;z-index:100}.history-panel.open{display:block}.history-panel h3{font-size:12px;color:var(--fg3);padding:10px 14px 6px;font-weight:600;position:sticky;top:0;background:var(--menu-bg)}.history-item{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:0.5px solid var(--border2);font-size:13px;cursor:pointer;transition:background .1s}.history-item:hover{background:var(--hover)}.history-item:last-child{border-bottom:none}.history-item .date{color:var(--fg);font-weight:500}.history-item .time{color:var(--fg3);font-size:11px;margin-left:8px}.history-item .del-btn{color:var(--fg3);font-size:11px;padding:2px 6px;border:1px solid var(--border2);border-radius:4px;background:transparent;cursor:pointer;opacity:0;transition:opacity .15s}.history-item:hover .del-btn{opacity:1}.history-item .del-btn:hover{color:#e55;border-color:#e55}.history-current{background:var(--hover)}.history-empty{padding:20px 14px;text-align:center;color:var(--fg3);font-size:12px}.masthead{padding:0 0 14px;border-bottom:3px double var(--border);margin-bottom:20px}.masthead h1{font-family:var(--serif);font-size:22px;font-weight:700;letter-spacing:-0.5px}.masthead .date{font-size:12px;color:var(--fg3);margin-top:3px}.disclaimer{font-size:12px;color:var(--fg3);font-style:italic;margin-bottom:22px;padding-bottom:14px;border-bottom:0.5px solid var(--border2)}.region{margin-bottom:32px}.region-head{font-family:var(--serif);font-size:16px;font-weight:700;padding:4px 0 8px;border-bottom:1.5px solid var(--border);margin-bottom:12px}.item{padding:10px 0 12px;border-bottom:0.5px solid var(--border2)}.item:last-child{border-bottom:none}.item-date{font-size:11px;color:var(--fg3)}.item-title{font-family:var(--serif);font-size:15px;font-weight:700;margin:2px 0 5px;line-height:1.5}.item-en{font-size:13px;color:var(--fg2);line-height:1.7;margin:0 0 4px}.item-jp{font-size:13px;color:var(--fg2);line-height:1.7;margin:0 0 4px}.item-zh{font-size:13px;line-height:1.6;margin:0 0 6px}.item-src{font-size:12.5px;color:var(--fg2);margin-top:4px}.item-src a{color:var(--link);text-decoration:none;border-bottom:0.5px solid transparent;font-weight:500}.item-src a:hover{border-bottom-color:var(--link)}.footer{margin-top:32px;padding-top:14px;border-top:3px double var(--border);font-size:11px;color:var(--fg3);text-align:center}"""

HISTORY_JS = '<script>\n(function(){\nvar B=window.location.href.replace(/\\/[^/]*$/,""),btn=document.getElementById("historyBtn"),panel=document.getElementById("historyPanel"),list=document.getElementById("historyList"),H=[],hid=JSON.parse(localStorage.getItem("hidden_dates")||"[]");\nbtn.onclick=function(e){e.stopPropagation();panel.classList.toggle("open");if(panel.classList.contains("open"))load();};\ndocument.onclick=function(){panel.classList.remove("open")};\npanel.onclick=function(e){e.stopPropagation()};\nfunction load(){fetch(B+"/history.json?"+Date.now()).then(function(r){return r.json()}).then(function(d){H=d.filter(function(x){return hid.indexOf(x.id)===-1});render()}).catch(function(){list.innerHTML=\'<div class="history-empty">暂无历史记录</div>\'})}\nfunction render(){if(!H.length){list.innerHTML=\'<div class="history-empty">暂无历史记录</div>\';return}var c=window.location.pathname.split("/").pop();list.innerHTML=H.map(function(h){var ic=(c===h.file||(c==="latest.html"&&h===H[0]));return \'<div class="history-item \'+(ic?"history-current":"")+\'" data-file="\'+h.file+\'"><div><span class="date">\'+h.date+\'</span><span class="time">\'+h.time+\'</span></div><div style="display:flex;align-items:center;gap:6px"><span class="items">\'+h.count+\' items</span><button class="del-btn" data-id="\'+h.id+\'">✕</button></div></div>\'}).join("");list.querySelectorAll(".history-item").forEach(function(el){el.onclick=function(){window.location.href=B+"/"+this.dataset.file}});list.querySelectorAll(".del-btn").forEach(function(el){el.onclick=function(e){e.stopPropagation();var id=this.dataset.id;hid.push(id);localStorage.setItem("hidden_dates",JSON.stringify(hid));H=H.filter(function(h){return h.id!==id});render()}})}\n})();\n</script>'

THEME_JS = '''<script>(function(){var root=document.documentElement,key="news-theme",media=window.matchMedia("(prefers-color-scheme: dark)");try{var saved=localStorage.getItem(key);if(saved==="light"||saved==="dark")root.dataset.theme=saved}catch(e){}function current(){return root.dataset.theme||(media.matches?"dark":"light")}function setup(){var button=document.getElementById("themeBtn"),icon=document.getElementById("themeIcon");if(!button||!icon)return;function render(){var dark=current()==="dark";icon.textContent=dark?"☀":"◐";button.title=dark?"切换到白色背景":"切换到黑色背景";button.setAttribute("aria-label",button.title);button.setAttribute("aria-pressed",dark?"true":"false")}button.onclick=function(){var next=current()==="dark"?"light":"dark";root.dataset.theme=next;try{localStorage.setItem(key,next)}catch(e){}render()};if(media.addEventListener)media.addEventListener("change",render);render()}if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",setup);else setup()})();</script>'''


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
            if title_a == title_b:
                continue
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

def normalized_story_headline(headline):
    value = strip_html(headline).lower()
    value = re.sub(r"\s*[（(][^）)]{1,40}[）)]\s*$", "", value)
    return re.sub(r"\W+", "", value)

def is_duplicate_story(headline, existing_headlines):
    candidate = normalized_story_headline(headline)
    if not candidate:
        return True
    for existing in existing_headlines:
        known = normalized_story_headline(existing)
        if candidate == known:
            return True
        if min(len(candidate), len(known)) >= 20 and SequenceMatcher(None, candidate, known).ratio() >= 0.9:
            return True
    return False

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
            root = ET.fromstring(fetch_rss_bytes(req))
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
            if is_duplicate_story(headline, [item["headline"] for item in items]):
                continue
            try:
                dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
            except Exception:
                continue
            if dt < NEWS_CUTOFF or dt > TODAY:
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


def is_relevant_market_item(sec, headline):
    lower = headline.lower()
    blocked = [
        "stock price, news, quote & history", "price prediction", "prediction:", "tokenized stock", "xstock",
        "no-brainer", "better buy", "is a buy now", "i'd buy", "top stocks", "top 5 picks", "dark horse",
        "best drone stocks", "how to invest", "could send", "could also crash", "in july", "mioeqy", "mshale",
        "international stock market performance", "to buy now",
        "株価・株式情報", "latest stock news and headlines", "share market live",
        "stocks to watch", "better ai buy", "screaming buy", "too late to buy",
        "could be worth", "investment split", "building a crypto portfolio",
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






def quote_body(sec, en_name, zh_name, price, pct, when):
    direction_en = "higher" if pct >= 0 else "lower"
    direction_jp = "上昇" if pct >= 0 else "下落"
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        return f"{zh_name}（{en_name}）は{when}時点で{fmt_price(price)}となり、前日終値比で{abs(pct):.2f}%{direction_jp}しています。"
    return f"{en_name} stood at {fmt_price(price)} as of {when}, {abs(pct):.2f}% {direction_en} than the previous close."

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
    if not ts:
        return None
    when = datetime.fromtimestamp(ts, timezone.utc).astimezone(LOCAL_TZ).strftime("%Y.%m.%d %H:%M JST")
    return {"symbol": symbol, "price": price, "prev": prev, "pct": pct, "time": when}

def fmt_price(value):
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:.2f}"

def quote_context(sec, en_name, zh_name, pct, when):
    direction = "上涨" if pct >= 0 else "下跌"
    return f"截至 {when}，{zh_name}较前收盘{direction}{abs(pct):.2f}%。"

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
        local_line = f"  行情日本語：{local_body}\n" if "日本" in sec["label"] or "Japan" in sec["label"] else f"  Quote: {local_body}\n"
        lines.append(
            f"- **[{q['time'].split()[0]}] 行情快照 / Quote · {en_name} — {zh_name}{direction}{abs(q['pct']):.2f}%**\n"
            f"{local_line}"
            f"  行情中文：{quote_context(sec, en_name, zh_name, q['pct'], q['time'])}\n"
            f"  📰 [Yahoo Finance](https://finance.yahoo.com/quote/{urllib.parse.quote(symbol, safe='')})"
        )
    return lines



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
            # Keep two readable alternates so a duplicated syndicated story can be
            # discarded after summarization without shrinking the section.
            items = enrich_articles(candidates)[:CONFIG["items_per_section"] + 2]
            if len(items) < 3:
                feeds = ["https://www.cnbc.com/id/100003114/device/rss/rss.html"]
                if "Japan" in sec["label"]:
                    feeds = ["https://rss.itmedia.co.jp/rss/2.0/monoist.xml"]
                extras = publisher_candidates(
                    feeds, NEWS_CUTOFF, TODAY,
                    lambda title: is_relevant_market_item(sec, title), fetch_rss_bytes,
                )
                extras = [i for i in extras if not is_duplicate_story(i["headline"], [j["headline"] for j in items])]
                for item in extras:
                    item["summary_language"] = "Japanese" if "Japan" in sec["label"] else "English"
                    item["section_label"] = sec["label"]
                items.extend(enrich_articles(extras[:12]))
        except Exception as ex:
            print(f"   {sec['emoji']} article fetch failed: {ex}")
            items = []
        grouped_items.append((sec, items))

    flat_items = [item for _, items in grouped_items for item in items]
    summarized = summarize_articles(flat_items, GEMINI_API_KEY, model=CONFIG["model"])
    summarized, removed = deduplicate_summaries(summarized)
    if removed:
        print(f"   Removed {len(removed)} duplicated syndicated summaries: {'; '.join(removed[:3])}")
    summarized, sentence_repairs = remove_repeated_summary_sentences(summarized)
    if sentence_repairs:
        print(f"   Repaired {len(sentence_repairs)} repeated syndicated sentences: {'; '.join(sentence_repairs[:3])}")
    issues = summary_quality_issues(summarized)
    if issues:
        raise RuntimeError("; ".join(issues[:5]))
    summarized_by_section = {}
    for item in summarized:
        summarized_by_section.setdefault(item["section_label"], []).append(item)

    published_items = []
    for sec, _ in grouped_items:
        items = summarized_by_section.get(sec["label"], [])[:CONFIG["items_per_section"]]
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
        if not lines:
            parts.append("> 当前时段暂无可核实的 24 小时内新稿（休市、假期或来源暂不可读）。其他板块已更新，未以行情或旧稿代替新闻。")
            continue
        published_items.extend(items)
        print(f"   {sec['label']}: {len(items)} news articles")
        # Quotes supplement news. Never count them toward the news requirement.
        lines.extend(market_snapshot_items(sec)[:2])
        parts.append("\n\n".join(lines))
    if len(published_items) < 3:
        raise RuntimeError("No readable fresh news across markets; keeping the previous complete edition")
    digest = "\n".join(parts)
    if not validate_digest_quality(digest):
        raise RuntimeError("Summary quality check failed; preserving previous edition")
    write_feed(OUTPUT_DIR, published_items, "market", TODAY, {s["label"]: 3 for s in CONFIG["sections"]})
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
    notices = {}
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("> "):
            if cur: notices[cur[1]] = s[2:].strip()
            else: discl = s[2:].strip()
        elif s.startswith("## "):
            if cur: regions.append((cur,items))
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
    if cur: regions.append((cur,items))
    parts = []
    for (f,l),its in regions:
        parts.append(f'<div class="region"><div class="region-head">{f} {l}</div>')
        if l in notices:
            parts.append(f'<p class="item-en">{html.escape(notices[l])}</p>')
        for it in its:
            en=jp=zh=src=""
            for ln in it["lines"]:
                if ln.startswith("Quote:"):
                    en = ln.split(":", 1)[1].strip()
                    continue
                if ln.startswith("行情日本語："):
                    jp = ln.split("：", 1)[1].strip()
                    continue
                if ln.startswith("行情中文："):
                    zh = ln.split("：", 1)[1].strip()
                    continue
                if ln.startswith("📰"): src=f'<div class="item-src">原文链接：{linkify(ln.replace("📰","").strip())}</div>'
                elif re.match(r"^(English|En)\s*[：:]", ln, re.I): en=re.split(r"[：:]",ln,maxsplit=1)[1].strip()
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
	<html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{T} | {DATE_STR}</title><style>{CSS}</style>{THEME_JS}</head><body>
	<div class="top-bar"><div class="history-wrap"><button class="history-btn" id="historyBtn"><svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 12.5A5.5 5.5 0 1 1 8 2.5a5.5 5.5 0 0 1 0 11zM8.5 4h-1v4.5l3.5 2 .5-.87-3-1.75V4z"/></svg>历史记录</button><div class="history-panel" id="historyPanel"><h3>📅 刷新记录</h3><div id="historyList"></div></div></div><div class="top-actions"><a href="https://roboticsdao.github.io/ai-robot-news/hub/#markets" style="font-size:12px;color:var(--link);white-space:nowrap">产业图谱</a><div class="updated-at">更新于 {TIME_STR} JST</div><button class="theme-btn" id="themeBtn" type="button"><span id="themeIcon" aria-hidden="true">◐</span></button></div></div>
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
