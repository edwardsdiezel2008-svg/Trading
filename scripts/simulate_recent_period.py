"""Simulate starting with a fixed amount of capital exactly N days ago and
running each strategy forward to today, using real market data.

Indicators still get a full-history warmup (run_backtest executes over the
entire bar history) so signals aren't degenerate at the start of the window -
only the capital base and reported P&L are reset to the window start. This
mirrors exactly how walkforward.py isolates a test fold's performance.

Usage:
  python scripts/simulate_recent_period.py --data data/raw/BTC_USDT_1D_bars.csv:BTC_USDT --freq 1D --days 30 --capital 100
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")

import pandas as pd

from src.backtest.data_loader import load_bars
from src.backtest.instruments import get_spec
from src.backtest.engine import run_backtest
from src.backtest.strategies import ALL_STRATEGY_CLASSES


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, help="'path:SYMBOL' pair")
    p.add_argument("--freq", default="1D")
    p.add_argument("--days", type=int, default=30, help="Bars back from the most recent bar to treat as the window start")
    p.add_argument("--capital", type=float, default=100.0)
    p.add_argument("--currency-label", default="CAD")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    path, symbol = args.data.rsplit(":", 1)
    bars = load_bars(path, freq=args.freq)
    spec = get_spec(symbol.upper())

    if args.days >= len(bars):
        raise SystemExit(f"--days ({args.days}) must be less than the available bar count ({len(bars)}).")

    window_start_idx = len(bars) - args.days
    window_start_time = bars.index[window_start_idx]
    window_end_time = bars.index[-1]

    rows = []
    for cls in ALL_STRATEGY_CLASSES:
        strat = cls()
        result = run_backtest(bars, strat, spec, initial_capital=args.capital)
        eq = result.equity_curve
        equity_at_window_start = eq.iloc[window_start_idx - 1] if window_start_idx > 0 else args.capital
        multiple = eq.iloc[-1] / equity_at_window_start if equity_at_window_start else 1.0
        simulated_final = args.capital * multiple
        profit = simulated_final - args.capital

        window_trades = [t for t in result.trades if window_start_time <= t.exit_time <= window_end_time]
        wins = [t for t in window_trades if t.net_pnl > 0]

        rows.append({
            "strategy": strat.name,
            f"final_{args.currency_label}": round(simulated_final, 2),
            f"profit_{args.currency_label}": round(profit, 2),
            "return_pct": round((multiple - 1) * 100, 2),
            "trades_in_window": len(window_trades),
            "win_rate": round(len(wins) / len(window_trades), 2) if window_trades else None,
            "position_now": "LONG" if result.positions.iloc[-1] > 0 else "SHORT" if result.positions.iloc[-1] < 0 else "FLAT",
        })

    table = pd.DataFrame(rows).sort_values(f"profit_{args.currency_label}", ascending=False).reset_index(drop=True)

    print(f"Simulating {args.capital:.2f} {args.currency_label} starting {window_start_time} through {window_end_time} ({args.days} bars, real {symbol} data)")
    print(f"NOTE: indicators are warmed up on the full {len(bars)}-bar history before this window; only the")
    print(f"capital base and P&L are reset to the window start. No FX conversion is modeled - {args.currency_label}")
    print("is a currency label only, applied to the same percentage math regardless of denomination.\n")
    print(table.to_string(index=False))
    return table


if __name__ == "__main__":
    main()
