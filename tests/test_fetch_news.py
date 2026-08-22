import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, ".")

from scripts.fetch_news import (
    _clean_text,
    _extract_image,
    _importance_score,
    _parse_pubdate,
    _tags_for,
    fetch_all_news,
    parse_feed,
)


def test_clean_text_strips_html_tags_and_collapses_whitespace():
    assert _clean_text("<p>Bitcoin  <b>surges</b>\n\tpast $100k</p>") == "Bitcoin surges past $100k"


def test_clean_text_handles_falsy_input():
    assert _clean_text(None) == ""
    assert _clean_text("") == ""


def test_parse_pubdate_parses_rfc822_and_normalizes_to_utc():
    dt = _parse_pubdate("Wed, 12 Aug 2026 10:00:00 -0400")
    assert dt.isoformat() == "2026-08-12T14:00:00+00:00"


def test_parse_pubdate_returns_none_for_missing_or_unparseable_input():
    assert _parse_pubdate(None) is None
    assert _parse_pubdate("") is None
    assert _parse_pubdate("not a date") is None


def test_tags_for_matches_case_insensitively_across_multiple_texts():
    tags = _tags_for("Bitcoin ETF inflows surge", "the SEC approved another fund")
    assert set(tags) == {"BTC", "ETF", "Regulation"}


def test_tags_for_returns_empty_when_nothing_matches():
    assert _tags_for("A totally unrelated headline about weather") == []


def test_tags_for_ignores_falsy_texts_without_crashing():
    assert _tags_for("Bitcoin rally", None, "") == ["BTC"]


def test_tags_for_matches_the_newer_defi_mining_exchange_and_nft_tags():
    tags = _tags_for("Binance exchange outflow spikes as DeFi yield farm exploited, NFT mint stalls")
    assert set(tags) == {"DeFi", "Exchange", "NFT"}
    assert _tags_for("Bitcoin miner hashrate hits new high") == ["BTC", "Mining"]
    assert _tags_for("Circle expands USDC stablecoin reserves") == ["Stablecoin"]


def test_importance_score_weights_regulation_etf_macro_above_core_coins_above_niche_tags():
    assert _importance_score(["Regulation"]) == 3
    assert _importance_score(["ETF"]) == 3
    assert _importance_score(["Macro"]) == 3
    assert _importance_score(["BTC"]) == 2
    assert _importance_score(["NFT"]) == 0
    assert _importance_score([]) == 0
    assert _importance_score(None) == 0


def test_importance_score_takes_the_max_across_multiple_tags():
    assert _importance_score(["NFT", "BTC", "Mining"]) == 2
    assert _importance_score(["BTC", "Regulation"]) == 3


_RSS_TEMPLATE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
{items}
</channel></rss>"""

_ITEM_TEMPLATE = """<item>
<title>{title}</title>
<link>{link}</link>
<description>{description}</description>
<pubDate>{pubdate}</pubDate>
</item>"""


def _rss(items):
    return ET.fromstring(_RSS_TEMPLATE.format(items="\n".join(items)))


def test_parse_feed_extracts_fields_and_tags_from_well_formed_items():
    root = _rss([_ITEM_TEMPLATE.format(
        title="Bitcoin ETF sees record inflows",
        link="https://example.com/a",
        description="<p>Institutional demand for BTC ETFs keeps climbing.</p>",
        pubdate="Wed, 12 Aug 2026 10:00:00 GMT",
    )])
    items = parse_feed("TestSource", root)
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Bitcoin ETF sees record inflows"
    assert item["link"] == "https://example.com/a"
    assert item["source"] == "TestSource"
    assert item["published_utc"] == "2026-08-12T10:00:00Z"
    assert set(item["tags"]) == {"BTC", "ETF"}


def test_parse_feed_skips_items_missing_a_title_or_link():
    root = _rss([
        _ITEM_TEMPLATE.format(title="", link="https://example.com/a", description="", pubdate=""),
        _ITEM_TEMPLATE.format(title="Has a title", link="", description="", pubdate=""),
        _ITEM_TEMPLATE.format(title="Valid item", link="https://example.com/c", description="", pubdate=""),
    ])
    items = parse_feed("TestSource", root)
    assert [it["title"] for it in items] == ["Valid item"]


def test_parse_feed_caps_at_max_per_feed(monkeypatch):
    import scripts.fetch_news as fetch_news
    monkeypatch.setattr(fetch_news, "MAX_PER_FEED", 2)
    root = _rss([
        _ITEM_TEMPLATE.format(title=f"Item {i}", link=f"https://example.com/{i}", description="", pubdate="")
        for i in range(5)
    ])
    items = fetch_news.parse_feed("TestSource", root)
    assert len(items) == 2


def test_fetch_all_news_dedupes_by_link_and_sorts_newest_first(monkeypatch):
    import scripts.fetch_news as fetch_news

    def fake_fetch_rss(url, retries=3, timeout=20):
        return {
            "https://feed-a": _rss([
                _ITEM_TEMPLATE.format(title="Older", link="https://example.com/x", description="", pubdate="Mon, 10 Aug 2026 00:00:00 GMT"),
                _ITEM_TEMPLATE.format(title="Newer", link="https://example.com/y", description="", pubdate="Wed, 12 Aug 2026 00:00:00 GMT"),
            ]),
            "https://feed-b": _rss([
                # Same link as "Older" above - a syndicated wire story from a second outlet.
                _ITEM_TEMPLATE.format(title="Older (syndicated)", link="https://example.com/x", description="", pubdate="Mon, 10 Aug 2026 00:00:00 GMT"),
            ]),
        }[url]

    monkeypatch.setattr(fetch_news, "FEEDS", [("A", "https://feed-a"), ("B", "https://feed-b")])
    monkeypatch.setattr(fetch_news, "_fetch_rss", fake_fetch_rss)

    items = fetch_all_news()
    assert [it["title"] for it in items] == ["Newer", "Older"]


def test_fetch_all_news_skips_a_feed_that_fails_without_crashing(monkeypatch):
    import scripts.fetch_news as fetch_news

    def fake_fetch_rss(url, retries=3, timeout=20):
        if url == "https://broken":
            raise RuntimeError("feed unreachable")
        return _rss([_ITEM_TEMPLATE.format(title="OK", link="https://example.com/ok", description="", pubdate="")])

    monkeypatch.setattr(fetch_news, "FEEDS", [("Broken", "https://broken"), ("Good", "https://good")])
    monkeypatch.setattr(fetch_news, "_fetch_rss", fake_fetch_rss)

    items = fetch_all_news()
    assert [it["title"] for it in items] == ["OK"]


def test_fetch_all_news_sorts_important_tags_ahead_of_more_recent_unimportant_ones(monkeypatch):
    # "SEC ruling" (Regulation, importance 3) is older than "New NFT drop"
    # (no importance tags) but must still sort first - and within the same
    # importance tier, recency still decides order (Newer BTC ahead of
    # Older BTC).
    import scripts.fetch_news as fetch_news

    def fake_fetch_rss(url, retries=3, timeout=20):
        return _rss([
            _ITEM_TEMPLATE.format(title="New NFT drop announced", link="https://example.com/nft", description="", pubdate="Thu, 13 Aug 2026 00:00:00 GMT"),
            _ITEM_TEMPLATE.format(title="SEC ruling on crypto custody", link="https://example.com/sec", description="", pubdate="Mon, 10 Aug 2026 00:00:00 GMT"),
            _ITEM_TEMPLATE.format(title="Bitcoin newer update", link="https://example.com/btc-new", description="", pubdate="Wed, 12 Aug 2026 00:00:00 GMT"),
            _ITEM_TEMPLATE.format(title="Bitcoin older update", link="https://example.com/btc-old", description="", pubdate="Tue, 11 Aug 2026 00:00:00 GMT"),
        ])

    monkeypatch.setattr(fetch_news, "FEEDS", [("A", "https://feed-a")])
    monkeypatch.setattr(fetch_news, "_fetch_rss", fake_fetch_rss)

    items = fetch_all_news()
    assert [it["title"] for it in items] == [
        "SEC ruling on crypto custody",
        "Bitcoin newer update",
        "Bitcoin older update",
        "New NFT drop announced",
    ]


_ENCLOSURE_ITEM = """<item>
<title>{title}</title>
<link>{link}</link>
<description>{description}</description>
<enclosure url="{image}" type="image/jpeg" length="12345"/>
</item>"""

_MEDIA_THUMB_ITEM = """<item xmlns:media="http://search.yahoo.com/mrss/">
<title>{title}</title>
<link>{link}</link>
<description></description>
<media:thumbnail url="{image}"/>
</item>"""

_MEDIA_CONTENT_ITEM = """<item xmlns:media="http://search.yahoo.com/mrss/">
<title>{title}</title>
<link>{link}</link>
<description></description>
<media:content url="{image}" medium="image"/>
</item>"""


def test_extract_image_prefers_an_image_type_enclosure():
    root = _rss([_ENCLOSURE_ITEM.format(title="A", link="https://example.com/a", description="", image="https://img.example.com/a.jpg")])
    item = root.find(".//item")
    assert _extract_image(item, "") == "https://img.example.com/a.jpg"


def test_extract_image_ignores_a_non_image_enclosure():
    non_image = _ENCLOSURE_ITEM.format(title="A", link="https://example.com/a", description="", image="https://example.com/a.mp3").replace('type="image/jpeg"', 'type="audio/mpeg"')
    root = _rss([non_image])
    item = root.find(".//item")
    assert _extract_image(item, "") is None


def test_extract_image_falls_back_to_media_thumbnail():
    root = _rss([_MEDIA_THUMB_ITEM.format(title="A", link="https://example.com/a", image="https://img.example.com/thumb.jpg")])
    item = root.find(".//item")
    assert _extract_image(item, "") == "https://img.example.com/thumb.jpg"


def test_extract_image_falls_back_to_media_content_when_medium_is_image():
    root = _rss([_MEDIA_CONTENT_ITEM.format(title="A", link="https://example.com/a", image="https://img.example.com/content.jpg")])
    item = root.find(".//item")
    assert _extract_image(item, "") == "https://img.example.com/content.jpg"


def test_extract_image_falls_back_to_inline_img_in_raw_description():
    root = _rss([_ITEM_TEMPLATE.format(title="A", link="https://example.com/a", description="", pubdate="")])
    item = root.find(".//item")
    raw = '<p><img src="https://img.example.com/inline.jpg" alt="x"></p>'
    assert _extract_image(item, raw) == "https://img.example.com/inline.jpg"


def test_extract_image_returns_none_when_nothing_is_present():
    root = _rss([_ITEM_TEMPLATE.format(title="A", link="https://example.com/a", description="plain text, no image", pubdate="")])
    item = root.find(".//item")
    assert _extract_image(item, "plain text, no image") is None


def test_parse_feed_includes_image_and_important_flag():
    root = _rss([_ENCLOSURE_ITEM.format(
        title="Bitcoin ETF sees record inflows", link="https://example.com/a", description="",
        image="https://img.example.com/a.jpg",
    )])
    item = parse_feed("TestSource", root)[0]
    assert item["image"] == "https://img.example.com/a.jpg"
    assert item["important"] is True

    root2 = _rss([_ITEM_TEMPLATE.format(title="Some unrelated headline", link="https://example.com/b", description="", pubdate="")])
    item2 = parse_feed("TestSource", root2)[0]
    assert item2["image"] is None
    assert item2["important"] is False


def test_fetch_rss_retries_then_succeeds(monkeypatch):
    import scripts.fetch_news as fetch_news

    calls = []

    class FakeResponse:
        content = b"<rss><channel></channel></rss>"

        def raise_for_status(self):
            pass

    def fake_get(url, timeout, headers):
        calls.append(url)
        if len(calls) < 3:
            raise ConnectionError("temporary network blip")
        return FakeResponse()

    monkeypatch.setattr(fetch_news.requests, "get", fake_get)
    monkeypatch.setattr(fetch_news.time, "sleep", lambda seconds: None)

    root = fetch_news._fetch_rss("https://example.com/feed", retries=3)

    assert len(calls) == 3
    assert root.tag == "rss"


def test_fetch_rss_raises_after_exhausting_all_retries(monkeypatch):
    import scripts.fetch_news as fetch_news

    def fake_get(url, timeout, headers):
        raise ConnectionError("feed is down")

    monkeypatch.setattr(fetch_news.requests, "get", fake_get)
    monkeypatch.setattr(fetch_news.time, "sleep", lambda seconds: None)

    try:
        fetch_news._fetch_rss("https://example.com/feed", retries=3)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "https://example.com/feed" in str(e)
        assert "after 3 attempts" in str(e)


def test_main_writes_news_json_from_fetch_all_news(tmp_path, monkeypatch):
    import json
    import os

    import scripts.fetch_news as fetch_news

    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    fake_items = [{"title": "Test headline", "link": "https://example.com/1", "tags": ["BTC"]}]
    monkeypatch.setattr(fetch_news, "fetch_all_news", lambda: fake_items)

    fetch_news.main()

    with open("paper_trading/news.json") as f:
        out = json.load(f)

    assert out["items"] == fake_items
    assert out["sources"] == [s for s, _ in fetch_news.FEEDS]
    assert "updated_at_utc" in out
