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
- For US Market and Macro sections, write a 300-500 character English body summary, not just a headline.
- For Japan Market, write a 300-500 character Japanese body summary.
- Always keep the Chinese auxiliary summary after the local-language body.
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
*{margin:0;padding:0;box-sizing:border-box}body{font-family:var(--sans);margin:0 auto;padding:28px 0;background:var(--bg);color:var(--fg);line-height:1.75;font-size:15px;-webkit-font-smoothing:antialiased;width:min(1180px,calc(100vw - 48px))}@media(max-width:760px){body{width:calc(100vw - 32px);padding:20px 0}}.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.history-wrap{position:relative}.history-btn{background:var(--menu-bg);border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-size:12px;color:var(--fg2);cursor:pointer;display:flex;align-items:center;gap:4px;font-family:var(--sans)}.history-btn:hover{background:var(--hover)}.history-btn svg{width:14px;height:14px;fill:var(--fg3)}.history-panel{display:none;position:absolute;top:36px;left:0;background:var(--menu-bg);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px var(--menu-shadow);min-width:280px;max-height:400px;overflow-y:auto;z-index:100}.history-panel.open{display:block}.history-panel h3{font-size:12px;color:var(--fg3);padding:10px 14px 6px;font-weight:600;position:sticky;top:0;background:var(--menu-bg)}.history-item{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:0.5px solid var(--border2);font-size:13px;cursor:pointer;transition:background .1s}.history-item:hover{background:var(--hover)}.history-item:last-child{border-bottom:none}.history-item .date{color:var(--fg);font-weight:500}.history-item .time{color:var(--fg3);font-size:11px;margin-left:8px}.history-item .del-btn{color:var(--fg3);font-size:11px;padding:2px 6px;border:1px solid var(--border2);border-radius:4px;background:transparent;cursor:pointer;opacity:0;transition:opacity .15s}.history-item:hover .del-btn{opacity:1}.history-item .del-btn:hover{color:#e55;border-color:#e55}.history-current{background:var(--hover)}.history-empty{padding:20px 14px;text-align:center;color:var(--fg3);font-size:12px}.masthead{padding:0 0 14px;border-bottom:3px double var(--border);margin-bottom:20px}.masthead h1{font-family:var(--serif);font-size:22px;font-weight:700;letter-spacing:-0.5px}.masthead .date{font-size:12px;color:var(--fg3);margin-top:3px}.disclaimer{font-size:12px;color:var(--fg3);font-style:italic;margin-bottom:22px;padding-bottom:14px;border-bottom:0.5px solid var(--border2)}.region{margin-bottom:32px}.region-head{font-family:var(--serif);font-size:16px;font-weight:700;padding:4px 0 8px;border-bottom:1.5px solid var(--border);margin-bottom:12px}.item{padding:10px 0 12px;border-bottom:0.5px solid var(--border2)}.item:last-child{border-bottom:none}.item-date{font-size:11px;color:var(--fg3)}.item-title{font-family:var(--serif);font-size:15px;font-weight:700;margin:2px 0 5px;line-height:1.5}.item-en{font-size:13px;color:var(--fg2);line-height:1.7;margin:0 0 4px}.item-jp{font-size:13px;color:var(--fg2);line-height:1.7;margin:0 0 4px}.item-zh{font-size:13px;line-height:1.6;margin:0 0 6px}.item-src{font-size:12.5px;color:var(--fg2);margin-top:4px}.item-src a{color:var(--link);text-decoration:none;border-bottom:0.5px solid transparent;font-weight:500}.item-src a:hover{border-bottom-color:var(--link)}.footer{margin-top:32px;padding-top:14px;border-top:3px double var(--border);font-size:11px;color:var(--fg3);text-align:center}"""

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

def mentioned_entities(headline):
    names = [
        "Nvidia", "Micron", "AMD", "Intel", "Qualcomm", "Broadcom", "Apple", "Microsoft", "Tesla",
        "Amazon", "Meta", "Alphabet", "Tokyo Electron", "Advantest", "Kioxia", "SoftBank",
        "Toyota", "Sony", "Nintendo", "USD/JPY", "Gold", "Oil", "Bitcoin",
    ]
    found = [name for name in names if name.lower() in headline.lower()]
    return "、".join(found[:5]) if found else "相关公司和板块"

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
    lower = headline.lower()
    section = sec["label"]
    entities = mentioned_entities(headline)
    if "美国" in section or "US" in section:
        if any(k in lower for k in ["micron", "nvidia", "amd", "qualcomm", "broadcom", "chip", "semiconductor"]):
            _, zh_points = us_event_points(headline)
            return (
                f"{entities} 是这条消息的主要观察对象。"
                + "；".join(zh_points)
                + "。交易上需要把标题里的具体催化和盘面反应分开看：如果同业、期货和成交量同步确认，说明资金正在沿 AI 芯片链扩散；如果只有单一股票反应，持续性就要打折。"
            )
        if any(k in lower for k in ["tesla", "rivian", "ev", "vehicle"]):
            return (
                f"{entities} 的变化会直接牵动美股电动车及高 beta 成长股情绪。"
                "Tesla 或同类公司的变化常会影响投资者对消费科技、自动驾驶、能源存储和成长股风险偏好的判断。"
                "如果消息涉及交付、价格、监管或分析师评级，通常会直接牵动期权交易和盘前波动；后续要看成交量、同业联动以及 Nasdaq 风险偏好是否跟随。"
            )
        if any(k in lower for k in ["apple", "microsoft", "amazon", "meta", "alphabet", "magnificent"]):
            return (
                f"{entities} 仍是大型科技股交易主线中的关键变量。"
                "这些公司权重高，对 S&P 500 和 Nasdaq 的方向影响明显；一旦估值、AI 投入、云业务或广告业务预期变化，指数可能被少数巨头牵引。"
                "接下来要看资金是继续集中在大型科技股，还是向软件、半导体设备、数据中心电力等周边产业扩散。"
            )
        return (
            f"{entities} 反映美股盘面或个股情绪正在发生变化。"
            "它的重点不只是指数涨跌，而是资金正在选择哪些行业、哪些主题以及哪些公司作为交易主线。"
            "后续应结合盘前期货、板块涨跌、成交量和分析师评级变化，判断这是短线情绪反弹，还是能够延续的产业趋势。"
        )
    if "日本" in section or "Japan" in section:
        if any(k in headline for k in ["半導体", "アドバンテスト", "東エレク", "東京エレクトロン", "キオクシア", "マイクロン", "AI"]):
            return (
                f"{entities} 把日本市场的焦点集中到半导体和 AI 产业链。"
                "日股中东京电子、Advantest、Kioxia、SoftBank Group 等常被视为 AI 基础设施和全球芯片周期的映射。"
                "如果海外芯片业绩或 AI 资本开支继续超预期，日经指数可能继续由高权重半导体股推动；同时也要留意日元和海外资金流向。"
            )
        return (
            f"{entities} 反映日本股市当天的行业轮动和个股表现。"
            "对日股来说，指数变化往往由半导体、汽车、金融、商社和 SoftBank 等权重股共同决定。"
            "需要结合日元走势、海外科技股表现、日银政策预期和外资买卖，判断行情是单日事件驱动，还是更广泛的趋势延续。"
        )
    if any(k in lower for k in ["dollar", "yen", "treasury", "yield", "fed", "rate"]):
        return (
            f"{entities} 正在影响美元、日元、美债收益率和全球风险资产定价。"
            "利率和汇率变化会通过折现率、企业融资成本和跨境资金流影响股票估值，尤其是高估值科技股和出口导向型日股。"
            "后续要观察 Fed 预期、美债收益率曲线、USD/JPY 以及黄金和比特币等避险/风险资产是否同步确认。"
        )
    if any(k in lower for k in ["oil", "gold", "bitcoin", "crypto"]):
        return (
            f"{entities} 属于需要和股市一起观察的跨资产信号。"
            "原油、黄金和比特币的变化会反映通胀预期、避险需求和风险偏好，对能源股、资源股、科技股估值和美元走势都有间接影响。"
            "如果这些资产与股指同向或背离，往往能提示市场是在交易增长、通胀，还是避险。"
        )
    return (
        f"{entities} 提供了判断股市趋势的背景变量。"
        "它需要和指数、行业轮动、汇率、利率和商品价格一起观察，才能判断资金是在追逐风险，还是降低仓位。"
        "对当天交易来说，最重要的是看该信号是否被美股科技股、日股半导体股和美元日元走势共同验证。"
    )

def ensure_summary_depth(summary, sec):
    if len(summary) >= 180:
        return summary
    if "美国" in sec["label"] or "US" in sec["label"]:
        extra = (
            "实盘上还应观察期货开盘后的成交量、期权隐含波动率、龙头股是否带动同业，以及资金是否从指数权重股扩散到中小型成长股。"
            "如果消息只推动单一公司而板块没有跟随，趋势持续性会弱一些；如果半导体、软件、云计算和电力基础设施同时响应，说明市场正在交易更完整的 AI 资本开支链条。"
        )
    elif "日本" in sec["label"] or "Japan" in sec["label"]:
        extra = (
            "实盘上还要结合日元汇率、外资买卖、美国科技股隔夜表现以及期货盘变化判断。"
            "如果日经上涨主要依赖少数半导体权重股，后续容易受海外芯片消息影响；如果汽车、金融、商社和中小盘也同步走强，说明市场宽度更健康。"
        )
    else:
        extra = (
            "实盘上要看该宏观信号是否同时影响美元、利率、商品和股指。"
            "如果美元与美债收益率继续上行，高估值科技股可能承压；如果黄金、原油或比特币与股市出现背离，则说明市场对通胀、避险或流动性的判断还不一致。"
        )
    return summary + extra

def english_market_body(sec, item, summary):
    headline = item["headline"]
    source = item.get("source", "the source")
    entities = mentioned_entities(headline).replace("、", ", ")
    if entities == "相关公司和板块":
        entities = "the relevant assets and sectors"
    lower = headline.lower()
    if "美国" in sec["label"] or "US" in sec["label"]:
        if any(k in lower for k in ["micron", "nvidia", "amd", "qualcomm", "broadcom", "chip", "semiconductor"]):
            theme = "AI chips, memory, data centers, and semiconductor equipment"
        elif any(k in lower for k in ["tesla", "rivian", "ev", "vehicle"]):
            theme = "electric vehicles, high-beta growth shares, and consumer technology"
        elif any(k in lower for k in ["apple", "microsoft", "amazon", "meta", "alphabet", "magnificent"]):
            theme = "mega-cap technology leadership and index concentration"
        else:
            theme = "index breadth, sector rotation, and risk appetite"
        if any(k in lower for k in ["micron", "nvidia", "amd", "qualcomm", "broadcom", "chip", "semiconductor", "ibm", "intel"]):
            en_points, _ = us_event_points(headline)
            return (
                f"Summary: {source} is reporting a specific {theme} story involving {entities}. "
                + " ".join(point[0].upper() + point[1:] + "." for point in en_points)
                + " The practical read-through is to compare the named stocks with Nasdaq futures, SOX-style semiconductor breadth, and opening volume. "
                "If the reaction spreads across peers, it supports a sector trade; if it stays isolated, it is more likely a short-term headline move."
            )
        return (
            f"Summary: {source} reports a market-moving item tied to {entities}. The relevance is how it feeds into {theme}. "
            f"Watch {entities} alongside Nasdaq futures, sector breadth, volume, and analyst revisions. "
            "If related stocks move together, the signal is more likely to reflect a real sector trend; if the reaction is isolated, it may be short-lived repricing. "
            "The next checkpoint is whether trading confirms the same direction across peers."
        )
    return (
        f"Summary: {source} highlights a cross-asset signal tied to {entities}. This matters because rates, currencies, commodities, and crypto all change the discount-rate and liquidity backdrop for risk assets. "
        f"Watch {entities} together with Treasury yields, USD/JPY, oil, gold, and major equity futures. "
        "If these indicators reinforce each other, the stock-market trend has stronger confirmation; if they diverge, investors may be rotating between growth, defensives, inflation hedges, and cash."
    )

def japanese_market_body(sec, item, summary):
    headline = item["headline"]
    source = item.get("source", "ニュースソース")
    entities = mentioned_entities(headline)
    if entities == "相关公司和板块":
        entities = "関連銘柄とセクター"
    return (
        f"要約：{source}の報道では、{entities}を中心に日本株の物色がどう広がるかが焦点です。"
        "半導体、AI、ソフトバンクグループ、輸出関連、金融などの主力株が同じ方向に動けば、日経平均やTOPIXの動きにも継続性が出やすくなります。"
        "一方で一部の値がさ株だけが上昇している場合は、市場全体の広がりが弱い可能性があります。次に見るべき点は、円相場、米国ハイテク株先物、出来高、海外投資家の買い姿勢です。"
        "決算やレーティング変更が材料の場合は、同業他社への波及も確認したいところです。指数寄与度の高い銘柄だけでなく、中小型株や内需株にも買いが広がるかを見ると、相場の持続力を判断しやすくなります。"
    )

def quote_body(sec, en_name, zh_name, price, pct, when):
    direction_en = "higher" if pct >= 0 else "lower"
    direction_jp = "上昇" if pct >= 0 else "下落"
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        return (
            f"要約：{zh_name}（{en_name}）は{when}時点で{fmt_price(price)}となり、前日比{abs(pct):.2f}%{direction_jp}しています。"
            "この価格変化は、日本株のなかで外部環境と個別材料がどの程度一致しているかを見る手がかりになります。"
            "半導体や大型輸出株が同時に強ければ、海外テック株や円安を背景にした買いが入りやすい一方、指数だけが動いて個別株の広がりが乏しい場合は短期的な反動にとどまる可能性があります。"
            "次は出来高、米国先物、円相場、同業銘柄の連動を確認する場面です。"
            "関連ニュースと価格方向が一致するかも重要です。"
        )
    if "美国" in sec["label"] or "US" in sec["label"]:
        return (
            f"Summary: {en_name} traded at {fmt_price(price)}, {abs(pct):.2f}% {direction_en} versus the previous close as of {when}. "
            "This live move is useful because it shows whether investors are rewarding the same theme that appears in the day’s news flow. "
            "For US equities, the key question is whether the move spreads from one index or company into semiconductors, software, cloud, EVs, or other growth-sensitive peers. "
            "If breadth and volume confirm it, the signal may support a stronger trend; if peers fail to follow, it is likely temporary."
        )
    return (
        f"Summary: {en_name} stood at {fmt_price(price)}, {abs(pct):.2f}% {direction_en} versus the previous close as of {when}. "
        "This matters for equities because macro prices shape the backdrop for valuation, liquidity, and risk appetite. "
        "Yields and currencies affect discount rates and exporter earnings, while oil, gold, and Bitcoin show whether investors are trading inflation, safety, or risk. "
        "Compare this move with US tech futures and broad equity indexes to see whether the message is confirmed."
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
    if "美国" in sec["label"] or "US" in sec["label"]:
        if en_name in {"NVIDIA", "AMD", "Broadcom", "Micron"}:
            theme = "AI 芯片和数据中心产业链"
        elif en_name in {"Apple", "Microsoft", "Tesla"}:
            theme = "大型科技股和成长股风险偏好"
        else:
            theme = "美股指数与市场宽度"
        return (
            f"截至 {when}，{zh_name}较前收盘{direction}{abs(pct):.2f}%。这类实时价格变化可以作为{theme}的即时温度计。"
            "如果相关个股与同板块新闻方向一致，说明资金正在围绕产业逻辑交易；如果价格和新闻背离，则可能是获利了结、估值压力或宏观利率因素压制。"
            "后续要结合成交量、盘前/盘中走势和同业联动，判断这只是短线波动，还是板块趋势的延续。"
        )
    if "日本" in sec["label"] or "Japan" in sec["label"]:
        return (
            f"截至 {when}，{zh_name}较前收盘{direction}{abs(pct):.2f}%。这对日本市场的意义在于，它能反映外资、日元汇率和全球科技周期对日股权重股的即时影响。"
            "若半导体或大型权重股同步走强，日经指数通常更容易被推升；若个股分化明显，则要警惕指数上涨背后的市场宽度不足。"
            "接下来应观察日元、美国科技股期货以及东京市场收盘后的海外反馈。"
        )
    return (
        f"截至 {when}，{zh_name}较前收盘{direction}{abs(pct):.2f}%。这个变化会影响股票市场的宏观定价背景。"
        "美元、利率、黄金、原油和比特币分别代表汇率压力、资金成本、避险需求、通胀预期和风险偏好。"
        "如果这些资产与股指方向相互印证，趋势可信度更高；如果出现背离，短线行情可能更容易反复。"
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
        summary = ensure_summary_depth(infer_market_summary(sec, item), sec)
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
            en=jp=zh=src=""
            for ln in it["lines"]:
                if ln.startswith("📰"): src=f'<div class="item-src">原文链接：{linkify(ln.replace("📰","").strip())}</div>'
                elif ln.lower().startswith("english:") or ln.lower().startswith("en:"): en=ln.split(":",1)[1].strip()
                elif ln.startswith("日本語:") or ln.startswith("日本語："): jp=re.split(r'[：:]',ln,1)[-1].strip()
                elif "中文" in ln[:4]: zh=re.split(r'[：:]',ln,1)[-1].strip()
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
