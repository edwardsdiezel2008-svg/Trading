import json
import os
import sys

sys.path.insert(0, ".")

import scripts.rug_watch as rug_watch
from scripts.build_paper_trading_dashboard import (
    SUFFIX_SYMBOL_FALLBACK,
    TRACK_META,
    TRACK_SUFFIXES,
    _cross_track_robustness,
    compute_cross_asset_robustness,
    compute_cross_futures_robustness,
    compute_rug_watch_summary,
    diversify_news,
    load_recent_bars,
    load_rug_watch_streaks,
)


def test_every_track_meta_suffix_has_a_symbol_fallback():
    # build_index_page() indexes SUFFIX_SYMBOL_FALLBACK by every TRACK_META
    # suffix whenever a track hasn't been seeded yet - a suffix missing here
    # is a KeyError at build time, not a graceful fallback. Caught for real
    # once when the NQ 1m/15m/1h tracks were added to TRACK_SUFFIXES/
    # TRACK_META without updating this map.
    missing = set(TRACK_META.keys()) - set(SUFFIX_SYMBOL_FALLBACK.keys())
    assert not missing, f"suffixes missing a symbol fallback: {missing}"


def test_every_track_suffix_has_meta():
    # TRACK_SUFFIXES drives placeholder generation; TRACK_META drives the
    # dashboard tab wiring and landing-page nav cards. A suffix present in
    # one but not the other silently drops that track from half the site.
    missing = set(TRACK_SUFFIXES) - set(TRACK_META.keys())
    assert not missing, f"suffixes missing from TRACK_META: {missing}"


def _wf_result(strategy, oos_return, oos_sharpe, error=None):
    r = {"strategy": strategy, "oos_total_return": oos_return, "oos_sharpe": oos_sharpe}
    if error:
        r["error"] = error
    return r


def test_cross_track_robustness_marks_an_asset_robust_only_when_return_and_sharpe_are_both_positive():
    loaded = {
        "_a": {"walkforward": {"results": [_wf_result("Trend", 10, 1.2)]}},
        "_b": {"walkforward": {"results": [_wf_result("Trend", 10, -0.5)]}},
    }
    out = _cross_track_robustness(loaded, [("A", "_a"), ("B", "_b")])
    assert len(out) == 1
    row = out[0]
    assert row["assets"] == {"A": True, "B": False}
    assert row["robust_count"] == 1
    assert row["assets_tested"] == 2


def test_cross_track_robustness_skips_errored_results():
    loaded = {
        "_a": {"walkforward": {"results": [_wf_result("Broken", 50, 2.0, error="insufficient data")]}},
        "_b": {"walkforward": {"results": [_wf_result("Broken", 10, 1.0)]}},
    }
    out = _cross_track_robustness(loaded, [("A", "_a"), ("B", "_b")])
    assert out[0]["assets"] == {"B": True}
    assert out[0]["assets_tested"] == 1


def test_cross_track_robustness_sorts_by_robust_count_then_strategy_name():
    loaded = {
        "_a": {"walkforward": {"results": [
            _wf_result("Zeta", 10, 1.0), _wf_result("Alpha", 10, 1.0), _wf_result("Beta", 10, 1.0),
        ]}},
        "_b": {"walkforward": {"results": [
            _wf_result("Zeta", -5, 1.0), _wf_result("Alpha", 10, 1.0), _wf_result("Beta", -5, 1.0),
        ]}},
    }
    out = _cross_track_robustness(loaded, [("A", "_a"), ("B", "_b")])
    # Alpha is robust on both (count 2, sorts first); Beta and Zeta are each
    # robust on only one - tied at count 1, so alphabetical breaks the tie.
    assert [r["strategy"] for r in out] == ["Alpha", "Beta", "Zeta"]


def test_cross_track_robustness_handles_a_track_with_no_walkforward_results():
    loaded = {
        "_a": {"walkforward": {"results": [_wf_result("Solo", 10, 1.0)]}},
        "_b": {"walkforward": {"results": []}},
    }
    out = _cross_track_robustness(loaded, [("A", "_a"), ("B", "_b")])
    assert out[0]["assets"] == {"A": True}
    assert out[0]["assets_tested"] == 1


def test_compute_cross_asset_robustness_uses_btc_eth_sol_daily_suffixes():
    loaded = {
        "": {"walkforward": {"results": [_wf_result("Trend", 10, 1.0)]}},
        "_eth": {"walkforward": {"results": [_wf_result("Trend", 10, 1.0)]}},
        "_sol": {"walkforward": {"results": [_wf_result("Trend", -5, 1.0)]}},
    }
    out = compute_cross_asset_robustness(loaded)
    assert out[0]["assets"] == {"BTC": True, "ETH": True, "SOL": False}


def test_compute_cross_futures_robustness_uses_all_six_daily_futures_suffixes():
    loaded = {
        suffix: {"walkforward": {"results": [_wf_result("Trend", 10, 1.0)]}}
        for suffix in ("_nq", "_es", "_ym", "_rty", "_gc", "_cl")
    }
    out = compute_cross_futures_robustness(loaded)
    assert out[0]["assets"] == {"NQ": True, "ES": True, "YM": True, "RTY": True, "GC": True, "CL": True}
    assert out[0]["robust_count"] == 6


def _write_bars_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")


def test_load_recent_bars_appends_volume_as_a_sixth_element(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bars_csv(
        "paper_trading/bars_zz.csv",
        ["timestamp", "open", "high", "low", "close", "volume"],
        [["2026-01-01", 100, 110, 90, 105, 12345]],
    )
    assert load_recent_bars("_zz") == [["2026-01-01", 100.0, 110.0, 90.0, 105.0, 12345.0]]


def test_load_recent_bars_stays_five_wide_without_a_volume_column(tmp_path, monkeypatch):
    # Backward compatibility: existing chart code destructures the first 5
    # fields positionally - a CSV that predates the volume column (or any
    # other bars file missing it) must not shift or break that.
    monkeypatch.chdir(tmp_path)
    _write_bars_csv(
        "paper_trading/bars_zz.csv",
        ["timestamp", "open", "high", "low", "close"],
        [["2026-01-01", 100, 110, 90, 105]],
    )
    assert load_recent_bars("_zz") == [["2026-01-01", 100.0, 110.0, 90.0, 105.0]]


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


def _coin(symbol, change_24h_pct, pct_from_24h_high):
    return {"symbol": symbol, "change_24h_pct": change_24h_pct, "pct_from_24h_high": pct_from_24h_high}


def test_rug_watch_summary_empty_when_nothing_crosses_thresholds():
    wide_scan = {"ranked": [_coin("A", 5, -2)], "not_moving": [_coin("B", -10, -12)]}
    summary = compute_rug_watch_summary(wide_scan)
    assert summary == {"flagged_count": 0, "severe_count": 0, "top_symbol": None}


def test_rug_watch_summary_flags_by_either_threshold():
    # WORST triggers on 24h change alone; DRAWDOWN triggers on drawdown-from-high alone.
    wide_scan = {
        "ranked": [],
        "not_moving": [_coin("WORST", -20, -5), _coin("DRAWDOWN", -1, -30), _coin("FINE", -5, -5)],
    }
    summary = compute_rug_watch_summary(wide_scan)
    assert summary["flagged_count"] == 2
    assert summary["severe_count"] == 0


def test_rug_watch_summary_counts_severe_separately_and_picks_the_worst_as_top():
    wide_scan = {
        "ranked": [],
        "not_moving": [_coin("MILD", -16, -10), _coin("CRASHED", -55, -60)],
    }
    summary = compute_rug_watch_summary(wide_scan)
    assert summary["flagged_count"] == 2
    assert summary["severe_count"] == 1
    assert summary["top_symbol"] == "CRASHED"


def _precise(symbol, drawdown_from_window_high_pct):
    return {"symbol": symbol, "drawdown_from_window_high_pct": drawdown_from_window_high_pct}


def test_rug_watch_summary_flags_a_coin_only_the_multiday_drawdown_catches():
    # SLIDER never crosses the 24h thresholds but has been grinding down for
    # days - only the precise-scan multi-day check should catch it.
    wide_scan = {"ranked": [], "not_moving": [_coin("SLIDER", -3, -5)]}
    memecoin_scan = {"ranked": [_precise("SLIDER", -35)]}
    summary = compute_rug_watch_summary(wide_scan, memecoin_scan)
    assert summary["flagged_count"] == 1
    assert summary["severe_count"] == 0
    assert summary["top_symbol"] == "SLIDER"


def test_rug_watch_summary_keeps_the_worse_severity_when_both_sources_flag_a_coin():
    # 24h check alone says elevated; the multi-day check on the same coin
    # says severe - the merge must keep severe, not silently downgrade it.
    wide_scan = {"ranked": [], "not_moving": [_coin("BOTH", -16, -10)]}
    memecoin_scan = {"ranked": [_precise("BOTH", -45)]}
    summary = compute_rug_watch_summary(wide_scan, memecoin_scan)
    assert summary["flagged_count"] == 1
    assert summary["severe_count"] == 1


def test_rug_watch_summary_does_not_downgrade_a_severe_24h_flag_with_a_milder_multiday_reading():
    wide_scan = {"ranked": [], "not_moving": [_coin("STRONG", -55, -60)]}
    memecoin_scan = {"ranked": [_precise("STRONG", -26)]}
    summary = compute_rug_watch_summary(wide_scan, memecoin_scan)
    assert summary["flagged_count"] == 1
    assert summary["severe_count"] == 1


def test_rug_watch_summary_ignores_precise_scan_rows_without_the_drawdown_field():
    wide_scan = {"ranked": [], "not_moving": []}
    memecoin_scan = {"ranked": [{"symbol": "NOFIELD"}]}
    summary = compute_rug_watch_summary(wide_scan, memecoin_scan)
    assert summary == {"flagged_count": 0, "severe_count": 0, "top_symbol": None}


def _write_history(path, runs):
    with open(path, "w") as f:
        json.dump({"runs": runs}, f)


def test_rug_watch_streaks_empty_without_a_history_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(tmp_path / "missing.json"))
    assert load_rug_watch_streaks() == {}


def test_rug_watch_streaks_counts_consecutive_runs_from_the_end(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(path))
    _write_history(path, [
        {"timestamp": "t0", "flagged": {"A": "elevated"}},
        {"timestamp": "t1", "flagged": {}},
        {"timestamp": "t2", "flagged": {"A": "elevated"}},
        {"timestamp": "t3", "flagged": {"A": "severe"}},
    ])
    # A was flagged in t3 and t2 (consecutive) but t1 broke the streak - t0
    # doesn't count even though A was flagged there too.
    assert load_rug_watch_streaks() == {"A": 2}


def test_rug_watch_streaks_only_reports_symbols_flagged_in_the_latest_run(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(path))
    _write_history(path, [
        {"timestamp": "t0", "flagged": {"STALE": "elevated"}},
        {"timestamp": "t1", "flagged": {"FRESH": "severe"}},
    ])
    assert load_rug_watch_streaks() == {"FRESH": 1}
