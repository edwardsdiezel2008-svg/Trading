import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, ".")

from scripts.fetch_news import _clean_text, _parse_pubdate, _tags_for, fetch_all_news, parse_feed


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
