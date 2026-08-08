"""Regenerate paper-trading state from the current bar history.

Deliberately has no incremental state logic: given paper_trading/bars.csv
(a growing, append-only file of real BTC daily bars), this just re-runs the
same tested backtest engine on the full history for every strategy and
derives "current position" from the last bar of a fresh, complete backtest.
That avoids an entire class of bugs that live-execution/incremental-update
code is prone to (state drift, double-counting, missed updates) - the
tradeoff is O(bars) work each run, which is trivial at this data size
(daily bars; even years of history is a few thousand rows).

This script does NOT fetch data itself - it has no network access here.
The bars file must already be updated with the latest candle(s) before
calling this (see paper_trading/README.md for the update procedure, which
requires the Crypto.com MCP connector, only callable by the agent, not a
plain script).

Usage: python scripts/paper_trade_update.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.metrics import compute_metrics
from src.backtest.strategies import ALL_STRATEGY_CLASSES

BARS_PATH = "paper_trading/bars.csv"
POSITIONS_PATH = "paper_trading/positions.json"
TRADE_LOG_PATH = "paper_trading/trade_log.csv"
SUMMARY_PATH = "paper_trading/summary.md"
CAPITAL = 100_000.0
SYMBOL = "BTC_USDT"


def main():
    bars = load_bars(BARS_PATH, freq="1D")
    spec = get_spec(SYMBOL)

    positions = {}
    all_trades = []
    summary_rows = []

    for cls in ALL_STRATEGY_CLASSES:
        strat = cls()
        result = run_backtest(bars, strat, spec, initial_capital=CAPITAL)
        metrics = compute_metrics(result, CAPITAL, freq_hint="1D")

        last_pos = int(result.positions.iloc[-1])
        last_equity = float(result.equity_curve.iloc[-1])
        open_trade = None
        if result.trades and result.trades[-1].exit_time == bars.index[-1] and last_pos != 0:
            # engine force-closes any still-open position at the final bar for
            # reporting purposes; if we're still holding as of the latest bar,
            # treat that synthetic close as "still open" for paper-trading state.
            t = result.trades[-1]
            open_trade = {"direction": t.direction, "entry_price": t.entry_price, "entry_time": str(t.entry_time)}
            closed_trades = result.trades[:-1]
        else:
            closed_trades = result.trades

        positions[strat.name] = {
            "position": last_pos,
            "position_label": "LONG" if last_pos > 0 else "SHORT" if last_pos < 0 else "FLAT",
            "equity": round(last_equity, 2),
            "open_trade": open_trade,
            "as_of": str(bars.index[-1]),
        }

        for t in closed_trades:
            all_trades.append({
                "strategy": strat.name,
                "direction": "LONG" if t.direction > 0 else "SHORT",
                "entry_time": str(t.entry_time),
                "exit_time": str(t.exit_time),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "net_pnl": round(t.net_pnl, 2),
            })

        summary_rows.append((strat.name, last_pos, last_equity, metrics["total_return"], metrics["sharpe"], metrics["num_trades"]))

    with open(POSITIONS_PATH, "w") as f:
        json.dump({
            "symbol": SYMBOL,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "latest_bar": str(bars.index[-1]),
            "strategies": positions,
        }, f, indent=2)

    import pandas as pd
    pd.DataFrame(all_trades).to_csv(TRADE_LOG_PATH, index=False)

    lines = [
        f"# BTC/USDT Paper Trading — updated {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Latest bar: {bars.index[-1]} · {len(bars):,} bars of history · ${CAPITAL:,.0f} starting capital per strategy",
        "",
        "| Strategy | Position | Equity | Total Return | Sharpe | Trades |",
        "|---|---|---|---|---|---|",
    ]
    for name, pos, equity, total_ret, sharpe, n_trades in sorted(summary_rows, key=lambda r: -r[3]):
        label = "LONG" if pos > 0 else "SHORT" if pos < 0 else "FLAT"
        sharpe_str = f"{sharpe:.2f}" if sharpe == sharpe else "—"  # NaN check
        lines.append(f"| {name} | {label} | ${equity:,.0f} | {total_ret*100:+.1f}% | {sharpe_str} | {n_trades} |")
    with open(SUMMARY_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Updated {POSITIONS_PATH}, {TRADE_LOG_PATH}, {SUMMARY_PATH}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
