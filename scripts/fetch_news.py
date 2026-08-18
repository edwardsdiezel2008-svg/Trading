"""Fetch crypto market news from public RSS feeds (no authentication
required) and write a tagged digest to paper_trading/news.json, sorted
newest-first within importance tiers (see IMPORTANCE_TAGS) rather than
pure recency - a headline tagged Regulation/ETF/Macro/BTC/ETH/SOL sorts
ahead of a same-age one that isn't.

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
# CryptoPanic) which now require a registered token. A feed that goes down
# or starts rejecting requests just drops out silently (see the per-feed
# try/except in fetch_all_news) rather than breaking the whole fetch, so
# this list can grow without each new entry needing a hard uptime guarantee.
FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Bitcoin.com", "https://news.bitcoin.com/feed/"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ("NewsBTC", "https://www.newsbtc.com/feed/"),
]

MAX_PER_FEED = 25
MAX_TOTAL = 100

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
    ("DeFi", ("defi", "decentralized finance", "liquidity pool", "yield farm")),
    ("Stablecoin", ("stablecoin", "usdt", "usdc", "tether", "circle ")),
    ("Mining", ("mining", "miner", "hashrate", "hash rate")),
    ("Exchange", ("binance", "coinbase", "kraken", "exchange hack", "exchange outflow")),
    ("NFT", ("nft", "non-fungible")),
]

# Tags whose presence makes a headline more likely to move the assets this
# site actually tracks - its core coins, plus categories (regulation, ETF
# flows, macro) that tend to move price broadly rather than affect one
# narrow niche. Used to sort important headlines ahead of same-recency ones
# that aren't tagged this way - a real, inspectable proxy built from the
# same tags already shown on every card, not a claim of objective
# "importance" from some external signal this project doesn't have.
IMPORTANCE_TAGS = {"Regulation": 3, "ETF": 3, "Macro": 3, "BTC": 2, "ETH": 2, "SOL": 2}

# RSS Media namespace (media:thumbnail / media:content) - several feeds
# (CryptoSlate, NewsBTC) carry article images this way instead of an
# <enclosure> or an inline <img> in <description>.
_MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def _importance_score(tags):
    return max((IMPORTANCE_TAGS.get(t, 0) for t in (tags or [])), default=0)


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


def _extract_image(item, description_raw):
    """Best-effort article image, checked in the order feeds are most
    likely to actually provide one: a proper <enclosure type="image/...">,
    then RSS Media's <media:thumbnail>/<media:content>, then finally an
    <img src> sniffed out of the raw (unstripped) description HTML - the
    same blob _clean_text strips tags from for the plain-text title match.
    Returns None rather than guessing when nothing looks like an image."""
    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = enclosure.get("url")
        if url and (enclosure.get("type") or "").startswith("image"):
            return url
    thumb = item.find(f"{_MEDIA_NS}thumbnail")
    if thumb is not None and thumb.get("url"):
        return thumb.get("url")
    content = item.find(f"{_MEDIA_NS}content")
    if content is not None and content.get("url"):
        medium = content.get("medium")
        typ = content.get("type") or ""
        if medium == "image" or typ.startswith("image"):
            return content.get("url")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description_raw or "", re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def parse_feed(source, xml_root):
    items = []
    for item in xml_root.findall(".//item")[:MAX_PER_FEED]:
        title = _clean_text(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        description_raw = item.findtext("description") or ""
        description = _clean_text(description_raw)
        published = _parse_pubdate(item.findtext("pubDate"))
        tags = _tags_for(title, description)
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "published_utc": published.isoformat().replace("+00:00", "Z") if published else "",
            "tags": tags,
            "image": _extract_image(item, description_raw),
            "important": _importance_score(tags) > 0,
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
    # Then a stable secondary sort by importance - Python's sort is stable,
    # so this reorders only across importance tiers and leaves the recency
    # order from above untouched within each tier, rather than needing to
    # re-specify the date as a tiebreaker.
    deduped.sort(key=lambda it: _importance_score(it["tags"]), reverse=True)
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
