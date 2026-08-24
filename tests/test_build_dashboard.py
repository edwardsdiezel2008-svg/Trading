import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, ".")

import scripts.rug_watch as rug_watch
from scripts.build_paper_trading_dashboard import (
    EMPTY_META_STRATEGY,
    EMPTY_POSITIONS,
    EMPTY_SENSITIVITY,
    EMPTY_WALKFORWARD,
    SUFFIX_SYMBOL_FALLBACK,
    TRACK_META,
    TRACK_SUFFIXES,
    TRACKS,
    _cross_track_robustness,
    _daily_returns,
    _pearson,
    build_backtest_lab_page,
    build_details_page,
    build_index_page,
    build_news_page,
    compute_correlations,
    compute_cross_asset_robustness,
    compute_cross_futures_robustness,
    compute_current_regimes,
    compute_rug_watch_summary,
    diversify_news,
    load_meta_strategy,
    load_recent_bars,
    load_rug_watch_streaks,
    load_sensitivity,
    load_track,
    load_walkforward,
    summarize_track,
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


def test_pearson_returns_none_below_two_points():
    assert _pearson({"d1": 1.0}, {"d1": 2.0}, ["d1"]) is None
    assert _pearson({}, {}, []) is None


def test_pearson_returns_none_when_either_series_has_zero_variance():
    # A flat series has zero variance - the correlation coefficient is
    # undefined (0/0), not 0. Must not raise ZeroDivisionError either.
    dates = ["d1", "d2", "d3"]
    flat = {"d1": 1.0, "d2": 1.0, "d3": 1.0}
    varying = {"d1": 1.0, "d2": 2.0, "d3": 3.0}
    assert _pearson(flat, varying, dates) is None
    assert _pearson(varying, flat, dates) is None


def test_pearson_perfect_positive_and_negative_correlation():
    dates = ["d1", "d2", "d3", "d4"]
    a = {"d1": 1.0, "d2": 2.0, "d3": 3.0, "d4": 4.0}
    same = {"d1": 10.0, "d2": 20.0, "d3": 30.0, "d4": 40.0}
    inverse = {"d1": -1.0, "d2": -2.0, "d3": -3.0, "d4": -4.0}
    assert _pearson(a, same, dates) == pytest.approx(1.0)
    assert _pearson(a, inverse, dates) == pytest.approx(-1.0)


def test_daily_returns_missing_file_is_empty():
    assert _daily_returns("paper_trading/does_not_exist.csv") == {}


def test_daily_returns_computes_pct_change_keyed_by_date(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = "paper_trading/bars_zz.csv"
    _write_bars_csv(
        path,
        ["timestamp", "open", "high", "low", "close", "volume"],
        [
            ["2026-01-01T00:00:00", 0, 0, 0, 100, 0],
            ["2026-01-02T00:00:00", 0, 0, 0, 110, 0],
            ["2026-01-03T00:00:00", 0, 0, 0, 99, 0],
        ],
    )
    returns = _daily_returns(path)
    assert returns == {
        "2026-01-02": pytest.approx(0.10),
        "2026-01-03": pytest.approx(-0.1),
    }


def test_daily_returns_skips_rows_with_zero_or_unparseable_close(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = "paper_trading/bars_zz.csv"
    _write_bars_csv(
        path,
        ["timestamp", "open", "high", "low", "close", "volume"],
        [
            ["2026-01-01T00:00:00", 0, 0, 0, 0, 0],  # zero close - can't divide by it
            ["2026-01-02T00:00:00", 0, 0, 0, 100, 0],
            ["2026-01-03T00:00:00", 0, 0, 0, "not-a-number", 0],  # dropped entirely
            ["2026-01-04T00:00:00", 0, 0, 0, 105, 0],
        ],
    )
    returns = _daily_returns(path)
    # 01-02 has no valid prior close (01-01's close is 0) so it's absent;
    # 01-03 never made it into `closes` at all; 01-04's prior valid close
    # is 01-02's 100.
    assert returns == {"2026-01-04": pytest.approx(0.05)}


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


def test_load_recent_bars_returns_empty_list_when_the_bars_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_recent_bars("_nope") == []


def test_load_recent_bars_skips_a_row_with_an_unparseable_price(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bars_csv(
        "paper_trading/bars_zz.csv",
        ["timestamp", "open", "high", "low", "close", "volume"],
        [["2026-01-01", "not-a-number", 110, 90, 105, 100], ["2026-01-02", 101, 111, 91, 106, 200]],
    )
    assert load_recent_bars("_zz") == [["2026-01-02", 101.0, 111.0, 91.0, 106.0, 200.0]]


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


def test_diversify_news_returns_early_once_the_primary_pass_alone_reaches_the_limit():
    # Six distinct sources, one item each, well under the per-source cap -
    # the primary pass fills `limit` on its own, so the function must
    # return right there rather than falling through to the (here,
    # unnecessary) backfill loop.
    items = [_item(f"S{i}", 0) for i in range(6)]
    top = diversify_news(items, limit=6, max_per_source=2)
    assert len(top) == 6
    assert {it["source"] for it in top} == {f"S{i}" for i in range(6)}


def test_build_news_page_embeds_the_full_feed_and_leaves_no_placeholder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/news_template.html", "w") as f:
        f.write("<html>__NEWS_JSON__</html>")

    news = {
        "updated_at_utc": "2026-08-18T12:00:00Z",
        "sources": ["CoinDesk"],
        "items": [{"title": "Bitcoin rallies", "link": "https://example.com/a", "source": "CoinDesk",
                    "published_utc": "2026-08-18T11:00:00Z", "tags": ["BTC"]}],
    }
    build_news_page(news)

    with open("paper_trading/news.html") as f:
        out = f.read()
    assert "__NEWS_JSON__" not in out
    assert "Bitcoin rallies" in out
    assert "CoinDesk" in out


def test_build_news_page_skips_gracefully_when_template_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    build_news_page({"updated_at_utc": None, "sources": [], "items": []})
    assert not os.path.exists("paper_trading/news.html")
    assert "Skipping" in capsys.readouterr().out


def test_build_backtest_lab_page_copies_template_through_unchanged(tmp_path, monkeypatch):
    # The template fetches backtest_lab.json itself at runtime (it's ~13MB -
    # too large to inline as a JS literal without blocking first paint on a
    # synchronous parse), so this build step no longer stitches anything
    # into the template; it just publishes it as-is once the JSON its
    # fetch() depends on actually exists.
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/backtest_lab_template.html", "w") as f:
        f.write("<html>fetch('backtest_lab.json')</html>")
    with open("paper_trading/backtest_lab.json", "w") as f:
        f.write('{"tracks":{},"strategies":{}}')

    build_backtest_lab_page()

    with open("paper_trading/backtest_lab.html") as f:
        out = f.read()
    assert out == "<html>fetch('backtest_lab.json')</html>"


def test_build_backtest_lab_page_skips_gracefully_when_template_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    build_backtest_lab_page()
    assert not os.path.exists("paper_trading/backtest_lab.html")
    assert "Skipping" in capsys.readouterr().out


def test_build_backtest_lab_page_skips_gracefully_when_json_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/backtest_lab_template.html", "w") as f:
        f.write("<html>fetch('backtest_lab.json')</html>")

    build_backtest_lab_page()

    assert not os.path.exists("paper_trading/backtest_lab.html")
    assert "run scripts/build_backtest_lab.py first" in capsys.readouterr().out


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


def test_rug_watch_summary_ignores_a_precise_scan_row_with_too_mild_a_drawdown():
    # A real drawdown value is present, but nowhere near either severity
    # threshold - distinct from the missing-field case above, this exercises
    # severity_for_multiday_drawdown actually returning None/falsy.
    wide_scan = {"ranked": [], "not_moving": []}
    memecoin_scan = {"ranked": [_precise("MILD", -4)]}
    summary = compute_rug_watch_summary(wide_scan, memecoin_scan)
    assert summary == {"flagged_count": 0, "severe_count": 0, "top_symbol": None}


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


def test_rug_watch_streaks_empty_when_the_history_file_has_no_runs_yet(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(path))
    _write_history(path, [])
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


def test_load_walkforward_missing_file_returns_empty_default():
    assert load_walkforward("_does_not_exist") == dict(EMPTY_WALKFORWARD)


def test_load_walkforward_reads_real_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/walkforward_zz.json", "w") as f:
        json.dump({"symbol": "BTC_USDT", "results": [{"strategy": "X"}]}, f)
    assert load_walkforward("_zz") == {"symbol": "BTC_USDT", "results": [{"strategy": "X"}]}


def test_load_sensitivity_missing_file_returns_empty_default():
    assert load_sensitivity("_does_not_exist") == dict(EMPTY_SENSITIVITY)


def test_load_sensitivity_reads_real_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/sensitivity_zz.json", "w") as f:
        json.dump({"results": [{"strategy": "Y"}]}, f)
    assert load_sensitivity("_zz") == {"results": [{"strategy": "Y"}]}


def test_load_meta_strategy_missing_file_returns_empty_default():
    assert load_meta_strategy("_does_not_exist") == dict(EMPTY_META_STRATEGY)


def test_load_meta_strategy_reads_real_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/meta_strategy_zz.json", "w") as f:
        json.dump({"current_regime": "trending/low_vol"}, f)
    assert load_meta_strategy("_zz") == {"current_regime": "trending/low_vol"}


def test_load_track_missing_positions_returns_empty_defaults():
    positions, trades, track_record = load_track("_does_not_exist")
    assert positions == dict(EMPTY_POSITIONS)
    assert trades == []
    assert track_record == []


def test_load_track_reads_and_types_real_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/positions_zz.json", "w") as f:
        json.dump({"symbol": "BTC_USDT", "strategies": {}}, f)
    _write_bars_csv(
        "paper_trading/trade_log_zz.csv",
        ["strategy", "net_pnl", "entry_price", "exit_price"],
        [["MA_Crossover", "12.5", "100", "101"]],
    )
    _write_bars_csv(
        "paper_trading/track_record_zz.csv",
        ["date", "strategy", "equity", "return_since_tracking_start_pct", "position"],
        [["2026-01-01", "MA_Crossover", "100500.0", "0.5", "1"]],
    )

    positions, trades, track_record = load_track("_zz")

    assert positions == {"symbol": "BTC_USDT", "strategies": {}}
    assert trades == [{"strategy": "MA_Crossover", "net_pnl": 12.5, "entry_price": 100.0, "exit_price": 101.0}]
    assert track_record[0]["equity"] == 100500.0
    assert track_record[0]["position"] == 1.0


def test_load_track_skips_track_record_when_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    with open("paper_trading/positions_zz.json", "w") as f:
        json.dump({"strategies": {}}, f)
    _write_bars_csv("paper_trading/trade_log_zz.csv", ["strategy", "net_pnl", "entry_price", "exit_price"], [])

    _, _, track_record = load_track("_zz")
    assert track_record == []


def test_summarize_track_reports_unseeded_when_no_strategies_yet():
    assert summarize_track({"strategies": {}}, "BTC Daily", "BTC/USDT") == {
        "label": "BTC Daily", "symbol": "BTC/USDT", "seeded": False,
    }


def test_summarize_track_ranks_strategies_and_floors_a_wiped_out_one_at_minus_100_pct():
    positions = {
        "updated_at_utc": "2026-01-01T00:00:00Z",
        "bar_count": 500,
        "leverage": 3.0,
        "buy_and_hold_equity_curve": [["2026-01-01", 100_000.0], ["2026-01-02", 105_000.0]],
        "strategies": {
            "Winner": {"equity": 120_000.0},
            "WipedOut": {"equity": -50.0},
            "Loser": {"equity": 90_000.0},
        },
    }
    summary = summarize_track(positions, "BTC Perp", "BTC/USDT")

    assert summary["seeded"] is True
    assert summary["total"] == 3
    assert summary["profitable"] == 1
    assert summary["best_name"] == "Winner"
    assert summary["best_return"] == pytest.approx(0.20)
    assert summary["buy_and_hold_return"] == pytest.approx(0.05)
    assert summary["leverage"] == 3.0


def test_summarize_track_buy_and_hold_return_is_none_without_a_curve():
    positions = {"strategies": {"Solo": {"equity": 100_000.0}}}
    summary = summarize_track(positions, "SOL Daily", "SOL/USDT")
    assert summary["buy_and_hold_return"] is None


def test_compute_correlations_pairs_up_assets_with_overlapping_return_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    _write_bars_csv(
        "paper_trading/bars.csv", ["timestamp", "open", "high", "low", "close", "volume"],
        [["2026-01-0%d" % d, 0, 0, 0, 100 + d, 0] for d in range(1, 6)],
    )
    _write_bars_csv(
        "paper_trading/bars_eth.csv", ["timestamp", "open", "high", "low", "close", "volume"],
        [["2026-01-0%d" % d, 0, 0, 0, 100 + d, 0] for d in range(1, 6)],
    )
    # SOL file absent - compute_correlations should just skip it, not crash.

    result = compute_correlations()

    assert set(result["assets"]) == {"BTC", "ETH"}
    assert len(result["pairs"]) == 1
    assert result["pairs"][0]["correlation"] == pytest.approx(1.0)  # identical price paths


def test_compute_current_regimes_skips_assets_with_no_bars_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    assert compute_current_regimes() == {}


def test_compute_current_regimes_reports_trend_vol_and_adx_for_an_available_asset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    n = 120
    # A steady uptrend with real high/low spread gives classify_regimes real
    # ADX/vol signal to report, rather than the NaN warmup a too-short or
    # degenerate (zero-range) series would produce.
    dates = pd.date_range("2026-01-01", periods=n, freq="1D")
    closes = [100 + d * 0.8 for d in range(n)]
    rows = [[dates[d].isoformat(), c - 0.5, c + 0.5, c - 1.0, c, 1000] for d, c in enumerate(closes)]
    _write_bars_csv("paper_trading/bars.csv", ["timestamp", "open", "high", "low", "close", "volume"], rows)

    regimes = compute_current_regimes()

    assert "BTC" in regimes
    assert regimes["BTC"]["trend_regime"] in {"trending", "ranging"}
    assert regimes["BTC"]["vol_regime"] in {"high_vol", "low_vol"}
    assert isinstance(regimes["BTC"]["adx"], float)


def test_compute_current_regimes_skips_an_asset_still_in_its_warmup_period(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    # Far too few bars for classify_regimes' rolling windows to have
    # produced a real (non-NaN) regime at the most recent bar yet.
    dates = pd.date_range("2026-01-01", periods=5, freq="1D")
    rows = [[d.isoformat(), 100, 101, 99, 100, 1000] for d in dates]
    _write_bars_csv("paper_trading/bars.csv", ["timestamp", "open", "high", "low", "close", "volume"], rows)

    assert compute_current_regimes() == {}


def test_compute_current_regimes_warns_and_continues_when_classification_raises(tmp_path, monkeypatch, capsys):
    import scripts.build_paper_trading_dashboard as build_paper_trading_dashboard

    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)
    # File exists (so the os.path.exists gate passes) but the actual
    # classification call fails - a real strategy is one bad/malformed
    # bars file shouldn't take the whole dashboard build down with it.
    _write_bars_csv("paper_trading/bars.csv", ["timestamp", "open", "high", "low", "close"], [["2026-01-01", 100, 101, 99, 100]])
    monkeypatch.setattr(
        build_paper_trading_dashboard, "classify_regimes",
        lambda bars: (_ for _ in ()).throw(RuntimeError("classification blew up")),
    )

    assert compute_current_regimes() == {}
    assert "WARN" in capsys.readouterr().out


def _make_loaded():
    """A minimal but complete `loaded` dict covering every real
    TRACK_SUFFIXES entry - what build_details_page/build_index_page expect
    main() to have already assembled from load_track/load_recent_bars/
    load_walkforward/etc. before either builder runs."""
    loaded = {}
    for suffix in TRACK_SUFFIXES:
        loaded[suffix] = {
            "positions": {"symbol": "BTC_USDT", "strategies": {}},
            "trades": [],
            "track_record": [],
            "bars": [],
            "walkforward": dict(EMPTY_WALKFORWARD),
            "sensitivity": dict(EMPTY_SENSITIVITY),
            "meta_strategy": dict(EMPTY_META_STRATEGY),
        }
    return loaded


def test_build_details_page_fills_every_placeholder_for_every_track(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)

    placeholders = ["__RUG_WATCH_STREAKS_JSON__"]
    for _, pos_key, trades_key, track_key, bars_key, wf_key, sens_key, meta_key in TRACKS:
        placeholders += [f"__{k}__" for k in (pos_key, trades_key, track_key, bars_key, wf_key, sens_key, meta_key)]
    for key in ("MEMECOIN_SCAN_JSON", "WIDE_MEMECOIN_SCAN_JSON", "BTC_MARKET_SNAPSHOT_JSON", "FEAR_GREED_JSON", "CORRELATIONS_JSON", "NEWS_JSON"):
        placeholders.append(f"__{key}__")
    with open("paper_trading/dashboard_template.html", "w") as f:
        f.write("<html>" + "\n".join(placeholders) + "</html>")

    build_details_page(
        _make_loaded(), memecoin_scan={"ranked": []}, wide_scan={"ranked": []},
        market_snapshot={"value": 1}, fear_greed={"value": 50}, correlations={"pairs": []}, news={"items": []},
    )

    # build_details_page's own internal assertions already confirm every
    # placeholder got filled (it would have raised otherwise) - just check
    # our data actually made it into the written file.
    with open("paper_trading/dashboard.html") as f:
        out = f.read()
    assert '"BTC_USDT"' in out
    assert '"value": 1' in out


def test_build_index_page_fills_every_placeholder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)

    index_placeholders = [
        "TRACK_SUMMARIES_JSON", "OVERVIEW_BARS_JSON", "BTC_MARKET_SNAPSHOT_JSON", "FEAR_GREED_JSON",
        "TOP_MOVERS_JSON", "WIDE_UNIVERSE_SIZE", "TOP_NEWS_JSON", "CROSS_ASSET_ROBUSTNESS_JSON",
        "CROSS_FUTURES_ROBUSTNESS_JSON", "SURVIVOR_STRESS_TEST_JSON", "REGIMES_JSON", "RUG_WATCH_JSON",
    ]
    with open("paper_trading/index_template.html", "w") as f:
        f.write("<html>" + "\n".join(f"__{k}__" for k in index_placeholders) + "</html>")

    build_index_page(
        _make_loaded(), wide_scan={"ranked": [], "not_moving": []}, memecoin_scan={"ranked": []},
        market_snapshot={}, fear_greed={}, news={"items": []}, regimes={}, survivor_stress_test={"results": []},
    )

    with open("paper_trading/index.html") as f:
        out = f.read()
    for key in index_placeholders:
        assert f"__{key}__" not in out


def test_build_index_page_skips_gracefully_when_template_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    os.makedirs("paper_trading", exist_ok=True)

    build_index_page(
        _make_loaded(), wide_scan={}, memecoin_scan={}, market_snapshot={}, fear_greed={},
        news={"items": []}, regimes={}, survivor_stress_test={},
    )

    assert not os.path.exists("paper_trading/index.html")
    assert "Skipping" in capsys.readouterr().out
