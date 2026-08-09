import sys

sys.path.insert(0, ".")

from scripts.build_paper_trading_dashboard import diversify_news


def _item(source, i):
    return {"source": source, "title": f"{source} story {i}", "link": f"https://x/{source}/{i}"}


def test_diversify_news_caps_a_dominant_source_in_the_primary_pass():
    # One source posts far more often than the other two - pure recency
    # sorting would let it fill the whole top-N. The primary pass must stop
    # picking from A once it hits the cap so B and C both get a slot;
    # backfill (uncapped, to guarantee a full `limit`) is then free to pull
    # more from A since only two other candidates exist.
    items = [_item("A", i) for i in range(10)] + [_item("B", 0)] + [_item("C", 0)]
    top = diversify_news(items, limit=6, max_per_source=2)
    counts = {}
    for it in top:
        counts[it["source"]] = counts.get(it["source"], 0) + 1
    assert len(top) == 6
    assert counts["B"] == 1
    assert counts["C"] == 1
    assert counts["A"] == 4  # 2 from the capped primary pass + 2 backfilled
    # The two B/C items must have made it in ahead of A's later, less-recent entries.
    assert top[2]["source"] == "B"
    assert top[3]["source"] == "C"


def test_diversify_news_backfills_to_reach_the_limit():
    # Not enough distinct sources to fill `limit` under the cap - backfill
    # from the same dominant source rather than returning a short list.
    items = [_item("A", i) for i in range(10)]
    top = diversify_news(items, limit=6, max_per_source=2)
    assert len(top) == 6
    assert all(it["source"] == "A" for it in top)


def test_diversify_news_preserves_recency_order_within_the_cap():
    items = [_item("A", i) for i in range(5)]
    top = diversify_news(items, limit=6, max_per_source=5)
    assert [it["title"] for it in top] == [it["title"] for it in items]
