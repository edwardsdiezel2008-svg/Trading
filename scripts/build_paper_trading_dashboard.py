"""Build both paper_trading HTML pages from current state:
  - paper_trading/index.html     - minimal live overview (the site root)
  - paper_trading/dashboard.html - full detailed dashboard (linked from index)

Run this after scripts/paper_trade_update.py whenever any track's state
changes.

Usage: python scripts/build_paper_trading_dashboard.py
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, ".")

import scripts.rug_watch as rug_watch
from src.backtest.data_loader import load_bars
from src.backtest.regime import classify_regimes

TEMPLATE_PATH = "paper_trading/dashboard_template.html"
OUTPUT_PATH = "paper_trading/dashboard.html"
INDEX_TEMPLATE_PATH = "paper_trading/index_template.html"
INDEX_OUTPUT_PATH = "paper_trading/index.html"
NEWS_TEMPLATE_PATH = "paper_trading/news_template.html"
NEWS_OUTPUT_PATH = "paper_trading/news.html"
BACKTEST_LAB_TEMPLATE_PATH = "paper_trading/backtest_lab_template.html"
BACKTEST_LAB_JSON_PATH = "paper_trading/backtest_lab.json"
BACKTEST_LAB_OUTPUT_PATH = "paper_trading/backtest_lab.html"
MEMECOIN_SCAN_PATH = "paper_trading/memecoin_scan.json"
WIDE_MEMECOIN_SCAN_PATH = "paper_trading/memecoin_wide_scan.json"
BTC_MARKET_SNAPSHOT_PATH = "paper_trading/btc_market_snapshot.json"
FEAR_GREED_PATH = "paper_trading/fear_greed.json"
NEWS_PATH = "paper_trading/news.json"
SURVIVOR_STRESS_TEST_PATH = "paper_trading/survivor_stress_test.json"
CAPITAL = 100_000.0

# Every track's template placeholder names follow one mechanical rule -
# UPPERCASE(suffix) spliced into POSITIONS{tag}_JSON etc. - so the whole
# TRACKS table (previously ~16 hand-written 8-tuples, one new line of
# copy-pasted boilerplate per track added) is generated from just the
# suffix list below. Adding a track is now a one-line change.
TRACK_SUFFIXES = [
    "", "_15m", "_eth", "_sol",
    "_perp", "_perp_15m", "_eth_perp", "_sol_perp",
    "_nq", "_nq5m", "_nq1m", "_nq15m", "_nq1h", "_es", "_es5m", "_ym", "_ym5m", "_gc", "_gc5m",
    "_rty", "_rty5m", "_cl", "_cl5m",
]


def _track_placeholder_keys(suffix: str) -> tuple[str, ...]:
    tag = suffix.upper()
    return (
        f"POSITIONS{tag}_JSON", f"TRADES{tag}_JSON", f"TRACK_RECORD{tag}_JSON",
        f"BARS{tag}_JSON", f"WALKFORWARD{tag}_JSON", f"SENSITIVITY{tag}_JSON", f"META_STRATEGY{tag}_JSON",
    )


# (file suffix, template placeholder prefix, bars placeholder, walk-forward placeholder, sensitivity placeholder, meta-strategy placeholder)
TRACKS = [(suffix, *_track_placeholder_keys(suffix)) for suffix in TRACK_SUFFIXES]

# suffix -> (hash-link key used by dashboard_template.html's tab wiring, nav label)
TRACK_META = {
    "": ("daily", "BTC Daily"),
    "_15m": ("fifteenMin", "BTC 15-Minute"),
    "_eth": ("eth", "ETH Daily"),
    "_sol": ("sol", "SOL Daily"),
    "_perp": ("perp", "BTC Perpetual"),
    "_perp_15m": ("perp15m", "BTC Perp 15-Min"),
    "_eth_perp": ("ethPerp", "ETH Perpetual"),
    "_sol_perp": ("solPerp", "SOL Perpetual"),
    "_nq": ("nq", "Nasdaq Futures (Daily)"),
    "_nq5m": ("nq5m", "Nasdaq Futures (5-Min)"),
    "_nq1m": ("nq1m", "Nasdaq Futures (1-Min)"),
    "_nq15m": ("nq15m", "Nasdaq Futures (15-Min)"),
    "_nq1h": ("nq1h", "Nasdaq Futures (1-Hour)"),
    "_es": ("es", "S&P 500 Futures (Daily)"),
    "_es5m": ("es5m", "S&P 500 Futures (5-Min)"),
    "_ym": ("ym", "Dow Futures (Daily)"),
    "_ym5m": ("ym5m", "Dow Futures (5-Min)"),
    "_gc": ("gc", "Gold Futures (Daily)"),
    "_gc5m": ("gc5m", "Gold Futures (5-Min)"),
    "_rty": ("rty", "Russell 2000 Futures (Daily)"),
    "_rty5m": ("rty5m", "Russell 2000 Futures (5-Min)"),
    "_cl": ("cl", "Crude Oil Futures (Daily)"),
    "_cl5m": ("cl5m", "Crude Oil Futures (5-Min)"),
}

# Fallback instrument symbol per suffix, used on the landing page nav cards
# only when a track hasn't been seeded yet (so positions.json has no
# "symbol" field to read from). Every TRACK_META suffix must have an entry
# here - a KeyError here is exactly what happens when a new track is wired
# into TRACK_SUFFIXES/TRACK_META but this fallback map is forgotten (caught
# for real once, adding the NQ 1m/15m/1h tracks - see the test that pins
# this invariant in tests/test_build_dashboard.py).
SUFFIX_SYMBOL_FALLBACK = {
    "": "BTC/USDT", "_15m": "BTC/USDT", "_eth": "ETH/USDT", "_sol": "SOL/USDT",
    "_perp": "BTC/USDT", "_perp_15m": "BTC/USDT", "_eth_perp": "ETH/USDT", "_sol_perp": "SOL/USDT",
    "_nq": "MNQ", "_nq5m": "MNQ", "_nq1m": "MNQ", "_nq15m": "MNQ", "_nq1h": "MNQ",
    "_es": "MES", "_es5m": "MES",
    "_ym": "MYM", "_ym5m": "MYM", "_gc": "MGC", "_gc5m": "MGC",
    "_rty": "M2K", "_rty5m": "M2K", "_cl": "MCL", "_cl5m": "MCL",
}

EMPTY_WALKFORWARD = {"symbol": None, "freq": None, "n_folds": 0, "generated_at_utc": None, "results": []}
EMPTY_SENSITIVITY = {"symbol": None, "freq": None, "generated_at_utc": None, "results": []}
EMPTY_META_STRATEGY = {
    "symbol": None, "freq": None, "generated_at_utc": None,
    "current_regime": None, "recommended_strategy": None, "live_regime_map": {},
    "oos_metrics": None, "folds": [],
}
EMPTY_POSITIONS = {"symbol": None, "freq": None, "updated_at_utc": None, "latest_bar": None, "bar_count": 0, "strategies": {}}
CHART_CANDLE_LIMIT = 200
OVERVIEW_BARS_LIMIT = 30


def load_walkforward(suffix):
    path = f"paper_trading/walkforward{suffix}.json"
    if not os.path.exists(path):
        return dict(EMPTY_WALKFORWARD)
    with open(path) as f:
        return json.load(f)


def load_sensitivity(suffix):
    path = f"paper_trading/sensitivity{suffix}.json"
    if not os.path.exists(path):
        return dict(EMPTY_SENSITIVITY)
    with open(path) as f:
        return json.load(f)


def load_meta_strategy(suffix):
    path = f"paper_trading/meta_strategy{suffix}.json"
    if not os.path.exists(path):
        return dict(EMPTY_META_STRATEGY)
    with open(path) as f:
        return json.load(f)


#  None of the leveraged (_perp*) tracks have a bars file of their own -
#  each is the same price history as its spot equivalent (paper_trade_
#  update.py --bars-file), just leveraged/liquidation-aware. Route reads
#  back to the spot suffix's file that actually exists instead of
#  duplicating it.
BARS_FILE_OVERRIDES = {"_perp": "", "_perp_15m": "_15m", "_eth_perp": "_eth", "_sol_perp": "_sol"}


def load_recent_bars(suffix, limit=CHART_CANDLE_LIMIT):
    """Tail of the raw OHLC(V) bars for the price chart - deliberately not the
    full multi-thousand-bar history (unreadable as candlesticks), just
    enough recent context to see actual price action alongside the
    strategy equity curves. Volume rides along as a 6th element so the
    futures tracks can show real recent-volume context on the dashboard -
    existing chart code destructures only the first 5 fields, so this is a
    backward-compatible addition, not a format change."""
    bars_suffix = BARS_FILE_OVERRIDES.get(suffix, suffix)
    path = f"paper_trading/bars{bars_suffix}.csv"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows[-limit:]:
        try:
            row = [r["timestamp"], float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])]
            if "volume" in r and r["volume"] not in (None, ""):
                row.append(float(r["volume"]))
            out.append(row)
        except (KeyError, ValueError, TypeError):
            continue
    return out


CORRELATION_ASSETS = [("BTC", "paper_trading/bars.csv"), ("ETH", "paper_trading/bars_eth.csv"), ("SOL", "paper_trading/bars_sol.csv")]


def _daily_returns(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        rows = list(csv.DictReader(f))
    closes = {}
    for r in rows:
        try:
            closes[r["timestamp"][:10]] = float(r["close"])
        except (KeyError, ValueError, TypeError):
            continue
    dates = sorted(closes)
    returns = {}
    for prev, cur in zip(dates, dates[1:]):
        if closes[prev]:
            returns[cur] = closes[cur] / closes[prev] - 1
    return returns


def _pearson(a, b, dates):
    xs = [a[d] for d in dates]
    ys = [b[d] for d in dates]
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def compute_correlations():
    """Pairwise Pearson correlation of daily returns across the tracked
    assets - answers whether ETH/SOL results are actually a diversified
    signal or just BTC beta, using data already fetched for the daily
    tracks (no new API calls)."""
    returns = {name: _daily_returns(path) for name, path in CORRELATION_ASSETS}
    returns = {name: r for name, r in returns.items() if r}
    names = list(returns.keys())
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = sorted(set(returns[a]) & set(returns[b]))
            corr = _pearson(returns[a], returns[b], common)
            if corr is not None:
                pairs.append({"a": a, "b": b, "correlation": round(corr, 3), "n": len(common)})
    return {"assets": names, "pairs": pairs}


def compute_current_regimes():
    """Latest ADX-based trend/volatility regime per asset - the same
    classify_regimes() used for backtest regime attribution, read at just
    its most recent bar. Context for *why* trend-following strategies
    (the ones that show up as cross-asset robust) are currently paying off
    or not: they need a trending regime to have anything to catch."""
    out = {}
    for name, path in CORRELATION_ASSETS:
        if not os.path.exists(path):
            continue
        try:
            bars = load_bars(path, freq="1D")
            regimes = classify_regimes(bars)
            last = regimes.iloc[-1]
            trend_regime, vol_regime, adx = last["trend_regime"], last["vol_regime"], last["adx"]
            if trend_regime != trend_regime or vol_regime != vol_regime:  # NaN check without a pandas import at call sites
                continue
            out[name] = {"trend_regime": trend_regime, "vol_regime": vol_regime, "adx": round(float(adx), 1)}
        except Exception as e:
            print(f"WARN: regime classification failed for {name}: {e}")
    return out


RUG_SEVERITY_RANK = {"elevated": 1, "severe": 2}


def compute_rug_watch_summary(wide_scan, memecoin_scan=None):
    """Lightweight landing-page summary of the Rug Pull Watch panel - just
    enough to show a warning badge on the Memecoin Scanner nav card without
    duplicating the full flagged-coin table there. Severity thresholds live
    in scripts/rug_watch.py, shared with memecoin_wide_scan.py's history
    logging (the full table on dashboard.html re-implements the same
    thresholds in JS, since that page has no build step to share with).

    Merges two signal sources, keeping the worse severity per symbol when
    both flag it: the 24h wide-scan snapshot, and (if memecoin_scan is
    given) the precise-scan coins' multi-day drawdown-from-window-high -
    mirrors dashboard_template.html's renderRugWatch() merge logic."""
    all_coins = (wide_scan.get("ranked") or []) + (wide_scan.get("not_moving") or [])
    by_symbol = {}
    for c in all_coins:
        sev = rug_watch.severity_for(c)
        if sev:
            by_symbol[c["symbol"]] = (c, sev)

    for p in (memecoin_scan or {}).get("ranked") or []:
        pct = p.get("drawdown_from_window_high_pct")
        if pct is None:
            continue
        sev = rug_watch.severity_for_multiday_drawdown(pct)
        if not sev:
            continue
        prior = by_symbol.get(p["symbol"])
        if prior and RUG_SEVERITY_RANK[prior[1]] >= RUG_SEVERITY_RANK[sev]:
            continue
        by_symbol[p["symbol"]] = (
            {"symbol": p["symbol"], "change_24h_pct": None, "pct_from_24h_high": pct},
            sev,
        )

    flagged = list(by_symbol.values())
    flagged.sort(key=lambda cs: min(cs[0].get("change_24h_pct") if cs[0].get("change_24h_pct") is not None else 0, cs[0].get("pct_from_24h_high", 0)))
    severe_count = sum(1 for _, sev in flagged if sev == "severe")
    top = flagged[0][0]["symbol"] if flagged else None
    return {"flagged_count": len(flagged), "severe_count": severe_count, "top_symbol": top}


def load_rug_watch_streaks():
    """For each symbol flagged in the most recent memecoin_wide_scan run,
    count consecutive prior runs (including the current one) it was also
    flagged in - a coin that's tripped the threshold for several hourly
    checks running is a much stronger signal than one that just crossed it
    once. Streak resets the moment a run doesn't have it flagged."""
    if not os.path.exists(rug_watch.HISTORY_PATH):
        return {}
    with open(rug_watch.HISTORY_PATH) as f:
        runs = json.load(f).get("runs", [])
    if not runs:
        return {}
    current_flagged = runs[-1].get("flagged", {})
    streaks = {}
    for symbol in current_flagged:
        streak = 0
        for run in reversed(runs):
            if symbol in (run.get("flagged") or {}):
                streak += 1
            else:
                break
        streaks[symbol] = streak
    return streaks


def diversify_news(items, limit=6, max_per_source=2):
    """The full news list is pure-recency sorted across several RSS feeds
    that don't post at the same rate - a single high-frequency outlet can
    fill most or all of a small top-N slice, crowding out the others
    entirely. Caps each source at max_per_source for the primary picks,
    then backfills any remaining slots by recency regardless of source so
    a short list (e.g. a quiet source with only one recent item) still
    always returns `limit` items when available."""
    picked, leftover, per_source = [], [], {}
    for it in items:
        src = it.get("source")
        if per_source.get(src, 0) < max_per_source:
            picked.append(it)
            per_source[src] = per_source.get(src, 0) + 1
        else:
            leftover.append(it)
        if len(picked) >= limit:
            return picked
    for it in leftover:
        picked.append(it)
        if len(picked) >= limit:
            break
    return picked


def load_track(suffix):
    positions_path = f"paper_trading/positions{suffix}.json"
    trade_log_path = f"paper_trading/trade_log{suffix}.csv"
    track_record_path = f"paper_trading/track_record{suffix}.csv"

    if not os.path.exists(positions_path):
        # New tracks (ETH/SOL) don't exist until their first successful
        # workflow run seeds them - render an empty track rather than crash.
        return dict(EMPTY_POSITIONS), [], []

    with open(positions_path) as f:
        positions = json.load(f)
    with open(trade_log_path) as f:
        trades = list(csv.DictReader(f))
    for t in trades:
        t["net_pnl"] = float(t["net_pnl"])
        t["entry_price"] = float(t["entry_price"])
        t["exit_price"] = float(t["exit_price"])

    track_record = []
    if os.path.exists(track_record_path):
        with open(track_record_path) as f:
            track_record = list(csv.DictReader(f))
        for r in track_record:
            r["equity"] = float(r["equity"])
            r["return_since_tracking_start_pct"] = float(r["return_since_tracking_start_pct"])
            r["position"] = float(r["position"])

    return positions, trades, track_record


def summarize_track(positions, label, symbol):
    """Lightweight per-track summary for the minimal landing page - avoids
    embedding full per-strategy equity curves/trade logs there, which
    belong on the detailed page only."""
    strategies = positions.get("strategies") or {}
    if not strategies:
        return {"label": label, "symbol": symbol, "seeded": False}

    rows = []
    for name, p in strategies.items():
        equity = p.get("equity") or 0
        total_return = -1.0 if equity <= 0 else (equity / CAPITAL - 1)
        rows.append({"name": name, "total_return": total_return})
    rows.sort(key=lambda r: -r["total_return"])
    profitable = sum(1 for r in rows if r["total_return"] > 0)

    bh_curve = positions.get("buy_and_hold_equity_curve") or []
    bh_return = (bh_curve[-1][1] / CAPITAL - 1) if bh_curve else None

    return {
        "label": label,
        "symbol": symbol,
        "seeded": True,
        "updated_at_utc": positions.get("updated_at_utc"),
        "bar_count": positions.get("bar_count", 0),
        "total": len(rows),
        "profitable": profitable,
        "best_name": rows[0]["name"],
        "best_return": rows[0]["total_return"],
        "buy_and_hold_return": bh_return,
        "leverage": positions.get("leverage", 1.0),
    }


def _cross_track_robustness(loaded, assets):
    """Shared helper: for a list of (label, suffix) pairs, cross-reference
    walk-forward robustness (positive OOS return AND positive OOS Sharpe)
    per strategy across all of them. Independent price histories agreeing
    is much harder to explain by chance than any single one working alone."""
    by_strategy = {}
    for asset, suffix in assets:
        for r in (loaded[suffix]["walkforward"].get("results") or []):
            if r.get("error"):
                continue
            row = by_strategy.setdefault(r["strategy"], {})
            row[asset] = bool(r.get("oos_total_return", 0) > 0 and r.get("oos_sharpe", 0) > 0)

    out = []
    for name, per_asset in by_strategy.items():
        robust_count = sum(1 for v in per_asset.values() if v)
        out.append({
            "strategy": name,
            "assets": per_asset,
            "robust_count": robust_count,
            "assets_tested": len(per_asset),
        })
    out.sort(key=lambda r: (-r["robust_count"], r["strategy"]))
    return out


def compute_cross_asset_robustness(loaded):
    """A strategy that's walk-forward-robust on one asset could just be that
    asset's history getting lucky. The stronger signal is a strategy that
    holds up out-of-sample on BTC AND ETH AND SOL independently - three
    different price histories agreeing is much harder to explain by chance
    than one. Cross-referenced across the three crypto daily tracks."""
    return _cross_track_robustness(loaded, [("BTC", ""), ("ETH", "_eth"), ("SOL", "_sol")])


def compute_cross_futures_robustness(loaded):
    """Same question, asked of the futures side of the cockpit: a strategy
    walk-forward-robust on one futures market could just be that market's
    10-year history getting lucky. Six independent futures markets (two
    large-cap equity indices, one small-cap index, one blue-chip index, and
    two commodities with very different drivers) agreeing is a much
    stronger signal than any single one - cross-referenced across
    NQ/ES/YM/RTY/GC/CL's daily tracks."""
    return _cross_track_robustness(loaded, [
        ("NQ", "_nq"), ("ES", "_es"), ("YM", "_ym"),
        ("RTY", "_rty"), ("GC", "_gc"), ("CL", "_cl"),
    ])


def build_details_page(loaded, memecoin_scan, wide_scan, market_snapshot, fear_greed, correlations, news):
    with open(TEMPLATE_PATH) as f:
        out = f.read()

    for suffix, pos_key, trades_key, track_key, bars_key, wf_key, sens_key, meta_key in TRACKS:
        d = loaded[suffix]
        out = out.replace(f"__{pos_key}__", json.dumps(d["positions"]))
        out = out.replace(f"__{trades_key}__", json.dumps(d["trades"]))
        out = out.replace(f"__{track_key}__", json.dumps(d["track_record"]))
        out = out.replace(f"__{bars_key}__", json.dumps(d["bars"]))
        out = out.replace(f"__{wf_key}__", json.dumps(d["walkforward"]))
        out = out.replace(f"__{sens_key}__", json.dumps(d["sensitivity"]))
        out = out.replace(f"__{meta_key}__", json.dumps(d["meta_strategy"]))

    out = out.replace("__MEMECOIN_SCAN_JSON__", json.dumps(memecoin_scan))
    out = out.replace("__WIDE_MEMECOIN_SCAN_JSON__", json.dumps(wide_scan))
    out = out.replace("__BTC_MARKET_SNAPSHOT_JSON__", json.dumps(market_snapshot))
    out = out.replace("__FEAR_GREED_JSON__", json.dumps(fear_greed))
    out = out.replace("__CORRELATIONS_JSON__", json.dumps(correlations))
    out = out.replace("__NEWS_JSON__", json.dumps(news))
    out = out.replace("__RUG_WATCH_STREAKS_JSON__", json.dumps(load_rug_watch_streaks()))

    for _, pos_key, trades_key, track_key, bars_key, wf_key, sens_key, meta_key in TRACKS:
        for key in (pos_key, trades_key, track_key, bars_key, wf_key, sens_key, meta_key):
            assert f"__{key}__" not in out, f"unfilled placeholder __{key}__"
    for key in ("MEMECOIN_SCAN_JSON", "WIDE_MEMECOIN_SCAN_JSON", "BTC_MARKET_SNAPSHOT_JSON", "FEAR_GREED_JSON", "CORRELATIONS_JSON", "NEWS_JSON", "RUG_WATCH_STREAKS_JSON"):
        assert f"__{key}__" not in out, f"unfilled placeholder __{key}__"

    with open(OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB)")


def build_index_page(loaded, wide_scan, memecoin_scan, market_snapshot, fear_greed, news, regimes, survivor_stress_test):
    if not os.path.exists(INDEX_TEMPLATE_PATH):
        print(f"Skipping {INDEX_OUTPUT_PATH}: {INDEX_TEMPLATE_PATH} not found")
        return

    with open(INDEX_TEMPLATE_PATH) as f:
        out = f.read()

    summaries = {}
    for suffix, (key, label) in TRACK_META.items():
        symbol = loaded[suffix]["positions"].get("symbol") or SUFFIX_SYMBOL_FALLBACK[suffix]
        summaries[key] = summarize_track(loaded[suffix]["positions"], label, symbol)
    out = out.replace("__TRACK_SUMMARIES_JSON__", json.dumps(summaries))

    overview_bars = {
        "BTC": loaded[""]["bars"][-OVERVIEW_BARS_LIMIT:],
        "ETH": loaded["_eth"]["bars"][-OVERVIEW_BARS_LIMIT:],
        "SOL": loaded["_sol"]["bars"][-OVERVIEW_BARS_LIMIT:],
    }
    out = out.replace("__OVERVIEW_BARS_JSON__", json.dumps(overview_bars))

    out = out.replace("__BTC_MARKET_SNAPSHOT_JSON__", json.dumps(market_snapshot))
    out = out.replace("__FEAR_GREED_JSON__", json.dumps(fear_greed))

    all_coins = (wide_scan.get("ranked") or []) + (wide_scan.get("not_moving") or [])
    top_movers = sorted(all_coins, key=lambda c: -abs(c.get("change_24h_pct", 0)))[:12]
    out = out.replace("__TOP_MOVERS_JSON__", json.dumps(top_movers))
    out = out.replace("__WIDE_UNIVERSE_SIZE__", json.dumps(wide_scan.get("universe_size", 0)))

    top_news = diversify_news(news.get("items") or [], limit=6, max_per_source=2)
    out = out.replace("__TOP_NEWS_JSON__", json.dumps(top_news))

    cross_asset_robustness = compute_cross_asset_robustness(loaded)
    out = out.replace("__CROSS_ASSET_ROBUSTNESS_JSON__", json.dumps(cross_asset_robustness))

    cross_futures_robustness = compute_cross_futures_robustness(loaded)
    out = out.replace("__CROSS_FUTURES_ROBUSTNESS_JSON__", json.dumps(cross_futures_robustness))

    out = out.replace("__SURVIVOR_STRESS_TEST_JSON__", json.dumps(survivor_stress_test))

    out = out.replace("__REGIMES_JSON__", json.dumps(regimes))

    rug_watch = compute_rug_watch_summary(wide_scan, memecoin_scan)
    out = out.replace("__RUG_WATCH_JSON__", json.dumps(rug_watch))

    for key in ("TRACK_SUMMARIES_JSON", "OVERVIEW_BARS_JSON", "BTC_MARKET_SNAPSHOT_JSON", "FEAR_GREED_JSON", "TOP_MOVERS_JSON", "WIDE_UNIVERSE_SIZE", "TOP_NEWS_JSON", "CROSS_ASSET_ROBUSTNESS_JSON", "CROSS_FUTURES_ROBUSTNESS_JSON", "SURVIVOR_STRESS_TEST_JSON", "REGIMES_JSON", "RUG_WATCH_JSON"):
        assert f"__{key}__" not in out, f"unfilled placeholder __{key}__"

    with open(INDEX_OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {INDEX_OUTPUT_PATH} ({os.path.getsize(INDEX_OUTPUT_PATH) / 1024:.1f} KB)")


def build_news_page(news):
    """Full news dashboard - every fetched headline (not just the small
    on-page panels' diversified/capped slices), with client-side search and
    source/tag filtering. Needs nothing but the news feed itself."""
    if not os.path.exists(NEWS_TEMPLATE_PATH):
        print(f"Skipping {NEWS_OUTPUT_PATH}: {NEWS_TEMPLATE_PATH} not found")
        return

    with open(NEWS_TEMPLATE_PATH) as f:
        out = f.read()

    out = out.replace("__NEWS_JSON__", json.dumps(news))
    assert "__NEWS_JSON__" not in out, "unfilled placeholder __NEWS_JSON__"

    with open(NEWS_OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {NEWS_OUTPUT_PATH} ({os.path.getsize(NEWS_OUTPUT_PATH) / 1024:.1f} KB)")


def build_backtest_lab_page():
    """Stitches the already-built paper_trading/backtest_lab.json (written
    separately by scripts/build_backtest_lab.py, which runs roughly 1,700
    real backtests and takes a few minutes - too slow to redo on every
    ordinary dashboard rebuild) into its page template. A no-op until that
    script has been run at least once."""
    if not os.path.exists(BACKTEST_LAB_TEMPLATE_PATH):
        print(f"Skipping {BACKTEST_LAB_OUTPUT_PATH}: {BACKTEST_LAB_TEMPLATE_PATH} not found")
        return
    if not os.path.exists(BACKTEST_LAB_JSON_PATH):
        print(f"Skipping {BACKTEST_LAB_OUTPUT_PATH}: {BACKTEST_LAB_JSON_PATH} not found "
              f"(run scripts/build_backtest_lab.py first)")
        return

    with open(BACKTEST_LAB_TEMPLATE_PATH) as f:
        out = f.read()
    with open(BACKTEST_LAB_JSON_PATH) as f:
        lab_json_text = f.read()

    out = out.replace("__BACKTEST_LAB_JSON__", lab_json_text)
    assert "__BACKTEST_LAB_JSON__" not in out, "unfilled placeholder __BACKTEST_LAB_JSON__"

    with open(BACKTEST_LAB_OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {BACKTEST_LAB_OUTPUT_PATH} ({os.path.getsize(BACKTEST_LAB_OUTPUT_PATH) / 1024 / 1024:.1f} MB)")


def main():
    loaded = {}
    for suffix, *_ in TRACKS:
        positions, trades, track_record = load_track(suffix)
        loaded[suffix] = {
            "positions": positions,
            "trades": trades,
            "track_record": track_record,
            "bars": load_recent_bars(suffix),
            "walkforward": load_walkforward(suffix),
            "sensitivity": load_sensitivity(suffix),
            "meta_strategy": load_meta_strategy(suffix),
        }

    memecoin_scan = {"ranked": [], "skipped": [], "updated_at_utc": None, "lookback_bars": 20, "atr_period": 14}
    if os.path.exists(MEMECOIN_SCAN_PATH):
        with open(MEMECOIN_SCAN_PATH) as f:
            memecoin_scan = json.load(f)

    wide_scan = {"ranked": [], "not_moving": [], "updated_at_utc": None, "universe_size": 0, "min_volume_usd": 10_000}
    if os.path.exists(WIDE_MEMECOIN_SCAN_PATH):
        with open(WIDE_MEMECOIN_SCAN_PATH) as f:
            wide_scan = json.load(f)

    market_snapshot = {"updated_at_utc": None, "order_book": None, "funding_rate": None}
    if os.path.exists(BTC_MARKET_SNAPSHOT_PATH):
        with open(BTC_MARKET_SNAPSHOT_PATH) as f:
            market_snapshot = json.load(f)

    fear_greed = {"updated_at_utc": None, "value": None, "classification": "", "timestamp": ""}
    if os.path.exists(FEAR_GREED_PATH):
        with open(FEAR_GREED_PATH) as f:
            fear_greed = json.load(f)

    news = {"updated_at_utc": None, "sources": [], "items": []}
    if os.path.exists(NEWS_PATH):
        with open(NEWS_PATH) as f:
            news = json.load(f)

    survivor_stress_test = {"generated_at_utc": None, "results": []}
    if os.path.exists(SURVIVOR_STRESS_TEST_PATH):
        with open(SURVIVOR_STRESS_TEST_PATH) as f:
            survivor_stress_test = json.load(f)
    # Total strategy-track walk-forward results scanned for statistical
    # significance - computed here so the dashboard's explanatory text
    # never goes stale when strategies or tracks are added/removed, the
    # way a hand-maintained count previously did.
    survivor_stress_test["total_checked"] = sum(
        len(loaded[s]["walkforward"].get("results") or []) for s in loaded
    )

    correlations = compute_correlations()
    regimes = compute_current_regimes()

    build_details_page(loaded, memecoin_scan, wide_scan, market_snapshot, fear_greed, correlations, news)
    build_index_page(loaded, wide_scan, memecoin_scan, market_snapshot, fear_greed, news, regimes, survivor_stress_test)
    build_news_page(news)
    build_backtest_lab_page()


if __name__ == "__main__":
    main()
