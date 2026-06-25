#!/usr/bin/env python3
"""
Stock Market News Digest — 日美股市新闻播报
Based on AI News Digest Automation Template v2
Dependencies: pip install google-genai
"""
import html, os, subprocess, re, sys, time, json, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
    "items_per_section": "4 to 8",
    "time_window": "today only",
    "section_prompt": """Search for {items_per_section} recent news specifically about {label}.
Search keywords: {keywords}. Today is {date_str}.
CRITICAL RULES:
- You MUST return {items_per_section} news items. NEVER return zero.
- Use TODAY'S market news only. Do NOT include older dates.
- Focus on: stock index movements, major earnings, central bank policy, notable stock movers, IPOs, M&A, analyst forecasts, market sentiment.
- NEVER say "sorry", "unable to find", "无法获取". FORBIDDEN.
- Each item MUST start with: - **[YYYY.MM.DD] Company/Index — Chinese summary**
- Source URL: direct article URLs only. NEVER use vertexaisearch URLs. Use publication homepage if unsure.
FORMAT:
- **[2026.06.19] S&P500 — 标普500指数创历史新高**
  English: One-line English summary.
  中文：一行中文摘要。
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
    "model": "gemini-2.5-flash",
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
*{margin:0;padding:0;box-sizing:border-box}body{font-family:var(--sans);margin:0 auto;padding:28px 24px;background:var(--bg);color:var(--fg);line-height:1.75;font-size:15px;-webkit-font-smoothing:antialiased;max-width:780px}@media(max-width:600px){body{padding:20px 16px}}.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.history-wrap{position:relative}.history-btn{background:var(--menu-bg);border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-size:12px;color:var(--fg2);cursor:pointer;display:flex;align-items:center;gap:4px;font-family:var(--sans)}.history-btn:hover{background:var(--hover)}.history-btn svg{width:14px;height:14px;fill:var(--fg3)}.history-panel{display:none;position:absolute;top:36px;left:0;background:var(--menu-bg);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px var(--menu-shadow);min-width:280px;max-height:400px;overflow-y:auto;z-index:100}.history-panel.open{display:block}.history-panel h3{font-size:12px;color:var(--fg3);padding:10px 14px 6px;font-weight:600;position:sticky;top:0;background:var(--menu-bg)}.history-item{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:0.5px solid var(--border2);font-size:13px;cursor:pointer;transition:background .1s}.history-item:hover{background:var(--hover)}.history-item:last-child{border-bottom:none}.history-item .date{color:var(--fg);font-weight:500}.history-item .time{color:var(--fg3);font-size:11px;margin-left:8px}.history-item .del-btn{color:var(--fg3);font-size:11px;padding:2px 6px;border:1px solid var(--border2);border-radius:4px;background:transparent;cursor:pointer;opacity:0;transition:opacity .15s}.history-item:hover .del-btn{opacity:1}.history-item .del-btn:hover{color:#e55;border-color:#e55}.history-current{background:var(--hover)}.history-empty{padding:20px 14px;text-align:center;color:var(--fg3);font-size:12px}.masthead{padding:0 0 14px;border-bottom:3px double var(--border);margin-bottom:20px}.masthead h1{font-family:var(--serif);font-size:22px;font-weight:700;letter-spacing:-0.5px}.masthead .date{font-size:12px;color:var(--fg3);margin-top:3px}.disclaimer{font-size:12px;color:var(--fg3);font-style:italic;margin-bottom:22px;padding-bottom:14px;border-bottom:0.5px solid var(--border2)}.region{margin-bottom:32px}.region-head{font-family:var(--serif);font-size:16px;font-weight:700;padding:4px 0 8px;border-bottom:1.5px solid var(--border);margin-bottom:12px}.item{padding:10px 0 12px;border-bottom:0.5px solid var(--border2)}.item:last-child{border-bottom:none}.item-date{font-size:11px;color:var(--fg3)}.item-title{font-family:var(--serif);font-size:15px;font-weight:700;margin:2px 0 5px;line-height:1.5}.item-en{font-size:13px;color:var(--fg2);line-height:1.6;margin:0 0 2px}.item-zh{font-size:13px;line-height:1.6;margin:0 0 6px}.item-src{font-size:12px;font-style:italic;color:var(--fg3)}.item-src a{color:var(--link);text-decoration:none;border-bottom:0.5px solid transparent}.item-src a:hover{border-bottom-color:var(--link)}.footer{margin-top:32px;padding-top:14px;border-top:3px double var(--border);font-size:11px;color:var(--fg3);text-align:center}"""

HISTORY_JS = '<script>\n(function(){\nvar B=window.location.href.replace(/\\/[^/]*$/,""),btn=document.getElementById("historyBtn"),panel=document.getElementById("historyPanel"),list=document.getElementById("historyList"),H=[],hid=JSON.parse(localStorage.getItem("hidden_dates")||"[]");\nbtn.onclick=function(e){e.stopPropagation();panel.classList.toggle("open");if(panel.classList.contains("open"))load();};\ndocument.onclick=function(){panel.classList.remove("open")};\npanel.onclick=function(e){e.stopPropagation()};\nfunction load(){fetch(B+"/history.json?"+Date.now()).then(function(r){return r.json()}).then(function(d){H=d.filter(function(x){return hid.indexOf(x.id)===-1});render()}).catch(function(){list.innerHTML=\'<div class="history-empty">暂无历史记录</div>\'})}\nfunction render(){if(!H.length){list.innerHTML=\'<div class="history-empty">暂无历史记录</div>\';return}var c=window.location.pathname.split("/").pop();list.innerHTML=H.map(function(h){var ic=(c===h.file||(c==="latest.html"&&h===H[0]));return \'<div class="history-item \'+(ic?"history-current":"")+\'" data-file="\'+h.file+\'"><div><span class="date">\'+h.date+\'</span><span class="time">\'+h.time+\'</span></div><div style="display:flex;align-items:center;gap:6px"><span class="items">\'+h.count+\' items</span><button class="del-btn" data-id="\'+h.id+\'">✕</button></div></div>\'}).join("");list.querySelectorAll(".history-item").forEach(function(el){el.onclick=function(){window.location.href=B+"/"+this.dataset.file}});list.querySelectorAll(".del-btn").forEach(function(el){el.onclick=function(e){e.stopPropagation();var id=this.dataset.id;hid.push(id);localStorage.setItem("hidden_dates",JSON.stringify(hid));H=H.filter(function(h){return h.id!==id});render()}})}\n})();\n</script>'

def call_gemini(prompt, use_search=True):
    from google import genai; from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = {"temperature": CONFIG["temperature"]}
    if use_search: cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    return (client.models.generate_content(model=CONFIG["model"],contents=prompt,config=types.GenerateContentConfig(**cfg)).text or "")

def has_real_content(t):
    if "- **[" not in t or "很抱歉" in t or "无法获取" in t or "sorry" in t.lower():
        return False
    dates = re.findall(r'-\s*\*\*\[(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})\]', t)
    normalized_today = DATE_STR.replace(".", "-")
    normalized_dates = [d.replace("/", "-").replace(".", "-") for d in dates]
    return bool(normalized_dates) and all(d == normalized_today for d in normalized_dates)

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
        params = {"q": f"{query} when:1d", "hl": hl, "gl": gl, "ceid": ceid}
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            root = ET.fromstring(response.read())

        for node in root.findall("./channel/item"):
            headline, source = parse_google_news_title(node.findtext("title", ""))
            link = node.findtext("link", "")
            published = node.findtext("pubDate", "")
            if not headline:
                continue
            combined = f"{headline} {source}"
            if any(term.lower() in combined.lower() for term in exclude_terms):
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
            if len(items) >= limit:
                return sorted(items, key=lambda x: x["dt"], reverse=True)
    return sorted(items, key=lambda x: x["dt"], reverse=True)

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
        lines.append(
            f"- **[{DATE_STR}] {en_name} — {zh_name}{direction}{abs(q['pct']):.2f}%**\n"
            f"  English: {en_name} was at {fmt_price(q['price'])}, {q['pct']:+.2f}% versus the previous close, as of {q['time']}.\n"
            f"  中文：截至 {q['time']}，{zh_name}报 {fmt_price(q['price'])}，较前收盘{direction}{abs(q['pct']):.2f}%。\n"
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
        lines.append(
            f"- **[{item['date']}] {item['source']} — {item['headline']}**\n"
            f"  English: {item['headline']}\n"
            f"  中文：新闻标题：{item['headline']}\n"
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
            if has_real_content(t): print(f"   {e} Got {t.count('- **')} items (attempt {a+1})"); return t
        except Exception as ex: print(f"   {e} Attempt {a+1} error: {ex}")
        time.sleep(CONFIG["retry_delay"])
    print(f"   {e} Fallback...")
    return fetch_section_rss(sec)

def generate_digest():
    h = f"# {CONFIG['emoji']} {CONFIG['title']} | {DATE_STR}（{WEEKDAY_JP}曜日 / {WEEKDAY_EN}）\n\n> {CONFIG['disclaimer']}\n\n---\n"
    parts = [h]
    for sec in CONFIG["sections"]:
        print(f"\n   Fetching {sec['emoji']} {sec['label']}...")
        c = fetch_section(sec)
        parts.append(f"\n## {sec['emoji']} {sec['label']}\n")
        parts.append(c if c else f"- **[{DATE_STR}] 暂无更新 — No updates**\n  English: No recent news.\n  中文：暂无新闻。")
        time.sleep(2)
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
            en=zh=src=""
            for ln in it["lines"]:
                if ln.startswith("📰"): src=f'<div class="item-src">📰 {linkify(ln.replace("📰","").strip())}</div>'
                elif ln.lower().startswith("english:") or ln.lower().startswith("en:"): en=ln.split(":",1)[1].strip()
                elif "中文" in ln[:4]: zh=re.split(r'[：:]',ln,1)[-1].strip()
                elif not en and not any('\u4e00'<=c<='\u9fff' for c in ln[:10]): en=ln
                elif not zh: zh=ln
            parts.append(f'<div class="item"><div class="item-date">{it["date"]}</div><div class="item-title">{it["title"]}</div>{"<p class=item-en>"+en+"</p>" if en else ""}{"<p class=item-zh>"+zh+"</p>" if zh else ""}{src}</div>')
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
    n=digest.count("- **"); OUTPUT_FILE.write_text(digest,encoding="utf-8")
    print(f"\n   Total: {n} items\n\n🌐 Publishing...")
    try: push_to_github(md_to_html(digest),n)
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)
    print("\n✅ Done!")
