"""Fetch crypto market news from public RSS feeds (no authentication
required) and write a tagged, recency-sorted digest to
paper_trading/news.json.

Same philosophy as fetch_market_data.py: plain HTTP, no API keys, meant to
run unattended from GitHub Actions so the dashboard's news feed stays fresh
independent of any Claude session being open.

Usage: python scripts/fetch_news.py
"""
from __future__ import annotations

import datetime
import email.utils
import json
import re
import time
import xml.etree.ElementTree as ET

import requests

# Well-known, public RSS feeds from mainstream crypto news outlets - no
# auth/API key needed, unlike most crypto news aggregator APIs (e.g.
# CryptoPanic) which now require a registered token.
FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Bitcoin.com", "https://news.bitcoin.com/feed/"),
]

MAX_PER_FEED = 15
MAX_TOTAL = 30

# Keyword -> tag shown on the dashboard. Checked against title (+
# description when present), case-insensitive. Order matters only for
# readability of the output tag list, not for matching.
TAG_KEYWORDS = [
    ("BTC", ("bitcoin", "btc")),
    ("ETH", ("ethereum", "eth ", "ether ")),
    ("SOL", ("solana", "sol ")),
    ("Regulation", ("sec ", "regulat", "lawsuit", "congress", "senate", "law ")),
    ("ETF", ("etf",)),
    ("Macro", ("federal reserve", "fed ", "interest rate", "inflation", "cpi", "jobs report")),
]


def _fetch_rss(url, retries=3, timeout=20):
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                url, timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; paper-trading-dashboard/1.0)"},
            )
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_err}")


def _clean_text(s):
    if not s:
        return ""
    # Strip any HTML tags some feeds embed in <description> (e.g. CoinTelegraph
    # wraps it in a <p>/<img> blob) - only the plain title is shown on the
    # dashboard, but the same cleaner is used for tag-matching text.
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_pubdate(raw):
    if not raw:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _tags_for(*texts):
    haystack = " ".join(t.lower() for t in texts if t)
    tags = []
    for tag, needles in TAG_KEYWORDS:
        if any(n in haystack for n in needles):
            tags.append(tag)
    return tags


def parse_feed(source, xml_root):
    items = []
    for item in xml_root.findall(".//item")[:MAX_PER_FEED]:
        title = _clean_text(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        description = _clean_text(item.findtext("description"))
        published = _parse_pubdate(item.findtext("pubDate"))
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "published_utc": published.isoformat().replace("+00:00", "Z") if published else "",
            "tags": _tags_for(title, description),
        })
    return items


def fetch_all_news():
    all_items = []
    for source, url in FEEDS:
        try:
            root = _fetch_rss(url)
            items = parse_feed(source, root)
            all_items.extend(items)
            print(f"{source}: {len(items)} items")
        except Exception as e:
            print(f"WARN: skipping {source} ({url}): {e}")

    # de-dupe by link (outlets occasionally syndicate the same wire story)
    seen = set()
    deduped = []
    for it in all_items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        deduped.append(it)

    # newest first; items with unparseable dates sort last rather than
    # crashing the sort or floating to the top.
    deduped.sort(key=lambda it: it["published_utc"] or "0000", reverse=True)
    return deduped[:MAX_TOTAL]


def main():
    items = fetch_all_news()
    payload = {
        "updated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "sources": [s for s, _ in FEEDS],
        "items": items,
    }
    with open("paper_trading/news.json", "w") as f:
        json.dump(payload, f, indent=2)
    print(f"news.json: {len(items)} items from {len(FEEDS)} sources")


if __name__ == "__main__":
    main()
