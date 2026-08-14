import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


MIN_ARTICLE_CHARS = 240
MAX_ARTICLE_CHARS = 4500
FORBIDDEN_ANALYSIS = (
    "后续应", "后续要看", "值得关注", "需要关注", "应关注", "投资者应",
    "商业指标", "量产节奏", "试点是否", "what to watch", "watch next",
)


def _ensure_article_dependencies():
    try:
        import googlenewsdecoder  # noqa: F401
        import trafilatura  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "googlenewsdecoder==0.1.7", "trafilatura==2.2.0"],
            check=True,
        )


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _extractive_summary(text, limit=520):
    text = _clean(text)
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    selected = []
    length = 0
    for sentence in sentences:
        if not sentence:
            continue
        if selected and length + len(sentence) > limit:
            break
        selected.append(sentence)
        length += len(sentence) + 1
        if length >= limit * 0.72:
            break
    return _clean(" ".join(selected)) or text[:limit].rstrip()


def _download_article(item):
    from googlenewsdecoder import gnewsdecoder
    from trafilatura import extract, fetch_url

    source_url = item.get("link", "")
    direct_url = source_url
    if "news.google.com" in source_url:
        decoded = gnewsdecoder(source_url, interval=1)
        if not decoded.get("status"):
            return None
        direct_url = decoded.get("decoded_url", "")
    if not direct_url:
        return None
    downloaded = fetch_url(direct_url)
    body = extract(
        downloaded,
        url=direct_url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    ) if downloaded else ""
    body = _clean(body)
    if len(body) < MIN_ARTICLE_CHARS:
        return None
    enriched = dict(item)
    enriched["link"] = direct_url
    enriched["article_text"] = body[:MAX_ARTICLE_CHARS]
    return enriched


def enrich_articles(items, workers=4):
    _ensure_article_dependencies()
    enriched = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_article, item): index for index, item in enumerate(items)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                article = future.result()
            except Exception as exc:
                print(f"   Article extraction failed: {items[index].get('headline', '')[:70]} ({exc})")
                article = None
            if article:
                enriched.append((index, article))
    enriched.sort(key=lambda pair: pair[0])
    return [article for _, article in enriched]


def _summary_prompt(items):
    payload = []
    for index, item in enumerate(items):
        payload.append({
            "id": str(index),
            "language": item.get("summary_language", "English"),
            "headline": item.get("headline", ""),
            "source": item.get("source", ""),
            "article_body": item.get("article_text", ""),
        })
    return f"""You are a precise news copy editor. Summarize each supplied ARTICLE BODY, not merely its headline.

Return only a valid JSON array. Each object must have exactly: id, local_summary, zh_summary.

Rules:
- Use only facts explicitly present in article_body. Do not add outside facts or guesses.
- Condense the full article's main event, parties, actions, key figures, reasons and stated context.
- Do not evaluate business prospects, investment meaning, commercialization, market implications, future indicators, or what readers should watch.
- Do not give advice, forecasts, conclusions about success, or generic industry commentary.
- You may include forecasts or opinions only when the article explicitly attributes them to a named person or organization; preserve that attribution.
- Preserve every number, date, percentage, currency and unit exactly. In zh_summary, keep expressions such as '$733 billion' or '$20 million' in their original notation instead of converting billion/million into 亿/万.
- local_summary must use the requested language. zh_summary must be Simplified Chinese.
- Aim for 300-500 characters in each field. If the article itself is short, be shorter rather than padding.
- Start directly with facts. Do not write meta phrases such as 'this article reports', 'this news concerns', or 'the headline says'.
- Every summary must be specific to its own article and must not reuse a closing sentence from another item.

ARTICLES:
{json.dumps(payload, ensure_ascii=False)}"""


def _parse_json_array(raw):
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("summary response is not a JSON array")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("summary response must be a list")
    return data


def _valid_summary(value):
    clean = _clean(value)
    lower = clean.lower()
    return len(clean) >= 40 and not any(phrase.lower() in lower for phrase in FORBIDDEN_ANALYSIS)


def _sanitize_summary(value):
    sentences = re.split(r"(?<=[.!?。！？])\s*", _clean(value))
    kept = [
        sentence for sentence in sentences
        if sentence and not any(phrase.lower() in sentence.lower() for phrase in FORBIDDEN_ANALYSIS)
    ]
    return _clean(" ".join(kept))


def _preserve_source_units(summary, article_text):
    for match in re.finditer(r"(?i)([$€£¥]?\s*\d[\d,.]*)\s+(million|billion|trillion)\b", article_text or ""):
        amount = _clean(match.group(1))
        unit = match.group(2).lower()
        original = f"{amount} {unit}"
        if re.search(re.escape(original), summary, re.I):
            continue
        number = re.sub(r"^[$€£¥]\s*", "", amount)
        localized = re.compile(
            rf"(?<![\d,.]){re.escape(number)}(?![\d,.])\s*(?:万亿|千亿|百亿|十亿|亿|千万|百万|十万|万)?\s*(?:美元|欧元|英镑|日元|人民币|元)",
            re.I,
        )
        summary, count = localized.subn(original, summary, count=1)
    return _clean(summary)


def repair_legacy_unit_corruption(value):
    repaired = value or ""
    embedded = re.compile(
        r"[$€£¥]?(\d[\d,]*)(?:\s*(?:million|billion|trillion))+(?=(?:\d|[,.]\d))",
        re.I,
    )
    for _ in range(3):
        updated = embedded.sub(r"\1", repaired)
        if updated == repaired:
            break
        repaired = updated
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    repaired = re.sub(
        rf"\b({months})\s+(\d{{1,2}})\s+(?:million|billion|trillion)(?=\s*[,，])",
        r"\1 \2",
        repaired,
        flags=re.I,
    )
    return repaired


def summarize_articles(items, api_key, model="gemini-3.5-flash-lite"):
    if not items:
        return []
    if api_key:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = _summary_prompt(items)
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                rows = {str(row.get("id")): row for row in _parse_json_array(response.text or "")}
                completed = []
                for index, item in enumerate(items):
                    row = rows.get(str(index), {})
                    local = _preserve_source_units(_sanitize_summary(row.get("local_summary", "")), item.get("article_text", ""))
                    chinese = _preserve_source_units(_sanitize_summary(row.get("zh_summary", "")), item.get("article_text", ""))
                    if not (_valid_summary(local) and _valid_summary(chinese)):
                        raise ValueError(f"invalid or analytical summary for item {index}")
                    current = dict(item)
                    current["local_summary"] = local
                    current["zh_summary"] = chinese
                    completed.append(current)
                return completed
            except Exception as exc:
                print(f"   Body-summary attempt {attempt + 1}/2 failed: {exc}")
                time.sleep(3)

    print("   Gemini summary unavailable; publishing factual source-language extracts without invented Chinese text")
    completed = []
    for item in items:
        current = dict(item)
        local = _extractive_summary(item.get("article_text", ""))
        current["local_summary"] = local
        current["zh_summary"] = local if item.get("summary_language") == "Chinese" else ""
        completed.append(current)
    return completed


def summary_quality_issues(items):
    issues = []
    seen = {}
    for item in items:
        for field in ("local_summary", "zh_summary"):
            value = _clean(item.get(field, ""))
            if not value:
                continue
            lower = value.lower()
            if any(phrase.lower() in lower for phrase in FORBIDDEN_ANALYSIS):
                issues.append(f"analytical template in {item.get('headline', '')}: {field}")
            normalized = re.sub(r"\W+", "", lower)
            if normalized in seen and seen[normalized] != item.get("headline"):
                issues.append(f"duplicate summary in {seen[normalized]} and {item.get('headline')}")
            seen[normalized] = item.get("headline")
    return issues
