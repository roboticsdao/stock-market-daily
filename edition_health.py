import json
import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request
from xml.etree import ElementTree as ET


def publisher_candidates(feeds, cutoff, now, relevant, fetch):
    items = []
    seen = set()
    for url in feeds:
        try:
            root = ET.fromstring(fetch(Request(url, headers={"User-Agent": "Mozilla/5.0"})))
            source = root.findtext("./channel/title") or urlsplit(url).hostname
            for node in root.findall("./channel/item"):
                title, link = node.findtext("title", ""), node.findtext("link", "")
                try:
                    dt = parsedate_to_datetime(node.findtext("pubDate", ""))
                    if dt.tzinfo is None:
                        continue
                    dt = dt.astimezone(now.tzinfo)
                except (ValueError, TypeError):
                    continue
                if not cutoff <= dt <= now or not relevant(title) or not link.startswith("https://") or link in seen:
                    continue
                seen.add(link)
                items.append({"date": dt.strftime("%Y.%m.%d"), "dt": dt,
                              "headline": title, "link": link, "source": source})
        except Exception as exc:
            print(f"   Publisher feed unavailable: {url} ({exc})")
    return sorted(items, key=lambda item: item["dt"], reverse=True)


def write_feed(directory, items, kind, now, goals):
    articles = []
    counts = {}
    for item in items:
        section = item.get("region_label") or item.get("section_label") or "Global"
        counts[section] = counts.get(section, 0) + 1
        articles.append({
            "date": item["date"], "published_at": item["dt"].isoformat(),
            "headline": item["headline"], "source": item["source"], "url": item["link"],
            "language": item.get("summary_language", "English"), "section": section,
            "summary": item.get("local_summary", ""), "summary_zh": item.get("zh_summary", ""),
        })
    if not articles:
        raise RuntimeError("No verified source articles; previous edition must be retained")
    missing = {label: {"target": goal, "actual": counts.get(label, 0)}
               for label, goal in goals.items() if counts.get(label, 0) < goal}
    translations_missing = sum(not a["summary_zh"] for a in articles)
    status = {"state": "partial" if missing or translations_missing else "ok", "checked_at": now.isoformat(),
              "latest_article_at": max(a["published_at"] for a in articles),
              "articles": len(articles), "sections": counts, "shortfalls": missing,
              "translations_missing": translations_missing}
    output = Path(directory)
    (output / "feed.json").write_text(json.dumps({
        "kind": kind, "updated_at": now.isoformat(), "status": status, "articles": articles
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status
