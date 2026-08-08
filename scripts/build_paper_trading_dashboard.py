"""Inject current paper_trading/positions.json + trade_log.csv into the
dashboard template, producing a self-contained HTML file ready to publish
as an Artifact. Run this after scripts/paper_trade_update.py whenever the
dashboard needs to reflect fresh state.

Usage: python scripts/build_paper_trading_dashboard.py
"""
from __future__ import annotations

import csv
import json
import os

TEMPLATE_PATH = "paper_trading/dashboard_template.html"
POSITIONS_PATH = "paper_trading/positions.json"
TRADE_LOG_PATH = "paper_trading/trade_log.csv"
OUTPUT_PATH = "paper_trading/dashboard.html"


def main():
    with open(TEMPLATE_PATH) as f:
        template = f.read()
    with open(POSITIONS_PATH) as f:
        positions = json.load(f)
    with open(TRADE_LOG_PATH) as f:
        trades = list(csv.DictReader(f))
    for t in trades:
        t["net_pnl"] = float(t["net_pnl"])
        t["entry_price"] = float(t["entry_price"])
        t["exit_price"] = float(t["exit_price"])

    out = template.replace("__POSITIONS_JSON__", json.dumps(positions))
    out = out.replace("__TRADES_JSON__", json.dumps(trades))
    assert "__POSITIONS_JSON__" not in out and "__TRADES_JSON__" not in out

    with open(OUTPUT_PATH, "w") as f:
        f.write(out)
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
