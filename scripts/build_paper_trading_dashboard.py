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

# (file suffix, template placeholder prefix)
TRACKS = [
    ("", "POSITIONS_JSON", "TRADES_JSON", "TRACK_RECORD_JSON"),
    ("_15m", "POSITIONS_15M_JSON", "TRADES_15M_JSON", "TRACK_RECORD_15M_JSON"),
]


def load_track(suffix):
    positions_path = f"paper_trading/positions{suffix}.json"
    trade_log_path = f"paper_trading/trade_log{suffix}.csv"
    track_record_path = f"paper_trading/track_record{suffix}.csv"

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

    assert "__POSITIONS_JSON__" not in out
    assert "__TRADES_JSON__" not in out
    assert "__TRACK_RECORD_JSON__" not in out
    assert "__POSITIONS_15M_JSON__" not in out
    assert "__TRADES_15M_JSON__" not in out
    assert "__TRACK_RECORD_15M_JSON__" not in out

    with open(OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
