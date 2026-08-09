"""Inject current paper_trading state (both the daily and 15-minute tracks)
into the dashboard template, producing a self-contained HTML file ready to
publish as an Artifact. Run this after scripts/paper_trade_update.py
whenever either track's state changes.

Usage: python scripts/build_paper_trading_dashboard.py
"""
from __future__ import annotations

import csv
import json
import os

TEMPLATE_PATH = "paper_trading/dashboard_template.html"
OUTPUT_PATH = "paper_trading/dashboard.html"
MEMECOIN_SCAN_PATH = "paper_trading/memecoin_scan.json"
WIDE_MEMECOIN_SCAN_PATH = "paper_trading/memecoin_wide_scan.json"
BTC_MARKET_SNAPSHOT_PATH = "paper_trading/btc_market_snapshot.json"
FEAR_GREED_PATH = "paper_trading/fear_greed.json"

# (file suffix, template placeholder prefix)
TRACKS = [
    ("", "POSITIONS_JSON", "TRADES_JSON", "TRACK_RECORD_JSON"),
    ("_15m", "POSITIONS_15M_JSON", "TRADES_15M_JSON", "TRACK_RECORD_15M_JSON"),
    ("_eth", "POSITIONS_ETH_JSON", "TRADES_ETH_JSON", "TRACK_RECORD_ETH_JSON"),
    ("_sol", "POSITIONS_SOL_JSON", "TRADES_SOL_JSON", "TRACK_RECORD_SOL_JSON"),
]

EMPTY_POSITIONS = {"symbol": None, "freq": None, "updated_at_utc": None, "latest_bar": None, "bar_count": 0, "strategies": {}}


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


def main():
    with open(TEMPLATE_PATH) as f:
        out = f.read()

    for suffix, pos_key, trades_key, track_key in TRACKS:
        positions, trades, track_record = load_track(suffix)
        out = out.replace(f"__{pos_key}__", json.dumps(positions))
        out = out.replace(f"__{trades_key}__", json.dumps(trades))
        out = out.replace(f"__{track_key}__", json.dumps(track_record))

    memecoin_scan = {"ranked": [], "skipped": [], "updated_at_utc": None, "lookback_bars": 20, "atr_period": 14}
    if os.path.exists(MEMECOIN_SCAN_PATH):
        with open(MEMECOIN_SCAN_PATH) as f:
            memecoin_scan = json.load(f)
    out = out.replace("__MEMECOIN_SCAN_JSON__", json.dumps(memecoin_scan))

    wide_scan = {"ranked": [], "not_moving": [], "updated_at_utc": None, "universe_size": 0, "min_volume_usd": 10_000}
    if os.path.exists(WIDE_MEMECOIN_SCAN_PATH):
        with open(WIDE_MEMECOIN_SCAN_PATH) as f:
            wide_scan = json.load(f)
    out = out.replace("__WIDE_MEMECOIN_SCAN_JSON__", json.dumps(wide_scan))

    market_snapshot = {"updated_at_utc": None, "order_book": None, "funding_rate": None}
    if os.path.exists(BTC_MARKET_SNAPSHOT_PATH):
        with open(BTC_MARKET_SNAPSHOT_PATH) as f:
            market_snapshot = json.load(f)
    out = out.replace("__BTC_MARKET_SNAPSHOT_JSON__", json.dumps(market_snapshot))

    fear_greed = {"updated_at_utc": None, "value": None, "classification": "", "timestamp": ""}
    if os.path.exists(FEAR_GREED_PATH):
        with open(FEAR_GREED_PATH) as f:
            fear_greed = json.load(f)
    out = out.replace("__FEAR_GREED_JSON__", json.dumps(fear_greed))

    assert "__POSITIONS_JSON__" not in out
    assert "__TRADES_JSON__" not in out
    assert "__TRACK_RECORD_JSON__" not in out
    assert "__POSITIONS_15M_JSON__" not in out
    assert "__TRADES_15M_JSON__" not in out
    assert "__TRACK_RECORD_15M_JSON__" not in out
    assert "__POSITIONS_ETH_JSON__" not in out
    assert "__TRADES_ETH_JSON__" not in out
    assert "__TRACK_RECORD_ETH_JSON__" not in out
    assert "__POSITIONS_SOL_JSON__" not in out
    assert "__TRADES_SOL_JSON__" not in out
    assert "__TRACK_RECORD_SOL_JSON__" not in out
    assert "__MEMECOIN_SCAN_JSON__" not in out
    assert "__WIDE_MEMECOIN_SCAN_JSON__" not in out
    assert "__BTC_MARKET_SNAPSHOT_JSON__" not in out
    assert "__FEAR_GREED_JSON__" not in out

    with open(OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
