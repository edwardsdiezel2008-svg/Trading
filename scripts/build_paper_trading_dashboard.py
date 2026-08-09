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

TEMPLATE_PATH = "paper_trading/dashboard_template.html"
OUTPUT_PATH = "paper_trading/dashboard.html"
INDEX_TEMPLATE_PATH = "paper_trading/index_template.html"
INDEX_OUTPUT_PATH = "paper_trading/index.html"
MEMECOIN_SCAN_PATH = "paper_trading/memecoin_scan.json"
WIDE_MEMECOIN_SCAN_PATH = "paper_trading/memecoin_wide_scan.json"
BTC_MARKET_SNAPSHOT_PATH = "paper_trading/btc_market_snapshot.json"
FEAR_GREED_PATH = "paper_trading/fear_greed.json"
NEWS_PATH = "paper_trading/news.json"
CAPITAL = 100_000.0

# (file suffix, template placeholder prefix, bars placeholder, walk-forward placeholder, sensitivity placeholder)
TRACKS = [
    ("", "POSITIONS_JSON", "TRADES_JSON", "TRACK_RECORD_JSON", "BARS_JSON", "WALKFORWARD_JSON", "SENSITIVITY_JSON"),
    ("_15m", "POSITIONS_15M_JSON", "TRADES_15M_JSON", "TRACK_RECORD_15M_JSON", "BARS_15M_JSON", "WALKFORWARD_15M_JSON", "SENSITIVITY_15M_JSON"),
    ("_eth", "POSITIONS_ETH_JSON", "TRADES_ETH_JSON", "TRACK_RECORD_ETH_JSON", "BARS_ETH_JSON", "WALKFORWARD_ETH_JSON", "SENSITIVITY_ETH_JSON"),
    ("_sol", "POSITIONS_SOL_JSON", "TRADES_SOL_JSON", "TRACK_RECORD_SOL_JSON", "BARS_SOL_JSON", "WALKFORWARD_SOL_JSON", "SENSITIVITY_SOL_JSON"),
]

# suffix -> (hash-link key used by dashboard_template.html's tab wiring, nav label)
TRACK_META = {
    "": ("daily", "BTC Daily"),
    "_15m": ("fifteenMin", "BTC 15-Minute"),
    "_eth": ("eth", "ETH Daily"),
    "_sol": ("sol", "SOL Daily"),
}

EMPTY_WALKFORWARD = {"symbol": None, "freq": None, "n_folds": 0, "generated_at_utc": None, "results": []}
EMPTY_SENSITIVITY = {"symbol": None, "freq": None, "generated_at_utc": None, "results": []}
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


def load_recent_bars(suffix, limit=CHART_CANDLE_LIMIT):
    """Tail of the raw OHLC bars for the price chart - deliberately not the
    full multi-thousand-bar history (unreadable as candlesticks), just
    enough recent context to see actual price action alongside the
    strategy equity curves."""
    path = f"paper_trading/bars{suffix}.csv"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows[-limit:]:
        try:
            out.append([r["timestamp"], float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])])
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
    }


def compute_cross_asset_robustness(loaded):
    """A strategy that's walk-forward-robust on one asset could just be that
    asset's history getting lucky. The stronger signal is a strategy that
    holds up out-of-sample on BTC AND ETH AND SOL independently - three
    different price histories agreeing is much harder to explain by chance
    than one. Same 'robust' definition the per-track panel uses (positive
    OOS return and positive OOS Sharpe), just cross-referenced across the
    three daily tracks here."""
    assets = [("BTC", ""), ("ETH", "_eth"), ("SOL", "_sol")]
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


def build_details_page(loaded, memecoin_scan, wide_scan, market_snapshot, fear_greed, correlations, news):
    with open(TEMPLATE_PATH) as f:
        out = f.read()

    for suffix, pos_key, trades_key, track_key, bars_key, wf_key, sens_key in TRACKS:
        d = loaded[suffix]
        out = out.replace(f"__{pos_key}__", json.dumps(d["positions"]))
        out = out.replace(f"__{trades_key}__", json.dumps(d["trades"]))
        out = out.replace(f"__{track_key}__", json.dumps(d["track_record"]))
        out = out.replace(f"__{bars_key}__", json.dumps(d["bars"]))
        out = out.replace(f"__{wf_key}__", json.dumps(d["walkforward"]))
        out = out.replace(f"__{sens_key}__", json.dumps(d["sensitivity"]))

    out = out.replace("__MEMECOIN_SCAN_JSON__", json.dumps(memecoin_scan))
    out = out.replace("__WIDE_MEMECOIN_SCAN_JSON__", json.dumps(wide_scan))
    out = out.replace("__BTC_MARKET_SNAPSHOT_JSON__", json.dumps(market_snapshot))
    out = out.replace("__FEAR_GREED_JSON__", json.dumps(fear_greed))
    out = out.replace("__CORRELATIONS_JSON__", json.dumps(correlations))
    out = out.replace("__NEWS_JSON__", json.dumps(news))

    for _, pos_key, trades_key, track_key, bars_key, wf_key, sens_key in TRACKS:
        for key in (pos_key, trades_key, track_key, bars_key, wf_key, sens_key):
            assert f"__{key}__" not in out, f"unfilled placeholder __{key}__"
    for key in ("MEMECOIN_SCAN_JSON", "WIDE_MEMECOIN_SCAN_JSON", "BTC_MARKET_SNAPSHOT_JSON", "FEAR_GREED_JSON", "CORRELATIONS_JSON", "NEWS_JSON"):
        assert f"__{key}__" not in out, f"unfilled placeholder __{key}__"

    with open(OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB)")


def build_index_page(loaded, wide_scan, market_snapshot, fear_greed, news):
    if not os.path.exists(INDEX_TEMPLATE_PATH):
        print(f"Skipping {INDEX_OUTPUT_PATH}: {INDEX_TEMPLATE_PATH} not found")
        return

    with open(INDEX_TEMPLATE_PATH) as f:
        out = f.read()

    summaries = {}
    for suffix, (key, label) in TRACK_META.items():
        symbol = loaded[suffix]["positions"].get("symbol") or {"": "BTC/USDT", "_15m": "BTC/USDT", "_eth": "ETH/USDT", "_sol": "SOL/USDT"}[suffix]
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

    top_news = (news.get("items") or [])[:6]
    out = out.replace("__TOP_NEWS_JSON__", json.dumps(top_news))

    cross_asset_robustness = compute_cross_asset_robustness(loaded)
    out = out.replace("__CROSS_ASSET_ROBUSTNESS_JSON__", json.dumps(cross_asset_robustness))

    for key in ("TRACK_SUMMARIES_JSON", "OVERVIEW_BARS_JSON", "BTC_MARKET_SNAPSHOT_JSON", "FEAR_GREED_JSON", "TOP_MOVERS_JSON", "WIDE_UNIVERSE_SIZE", "TOP_NEWS_JSON", "CROSS_ASSET_ROBUSTNESS_JSON"):
        assert f"__{key}__" not in out, f"unfilled placeholder __{key}__"

    with open(INDEX_OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {INDEX_OUTPUT_PATH} ({os.path.getsize(INDEX_OUTPUT_PATH) / 1024:.1f} KB)")


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

    correlations = compute_correlations()

    build_details_page(loaded, memecoin_scan, wide_scan, market_snapshot, fear_greed, correlations, news)
    build_index_page(loaded, wide_scan, market_snapshot, fear_greed, news)


if __name__ == "__main__":
    main()
