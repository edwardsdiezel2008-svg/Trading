"""Regenerate paper-trading state from the current bar history, for a given
track (timeframe).

Deliberately has no incremental state logic: given a growing, append-only
bars CSV, this just re-runs the same tested backtest engine on the full
history for every strategy and derives "current position" from the last bar
of a fresh, complete backtest. That avoids an entire class of bugs that
live-execution/incremental-update code is prone to (state drift, double-
counting, missed updates) - the tradeoff is O(bars) work each run, trivial
at these data sizes.

This script does NOT fetch data itself - it has no network access here. The
bars file must already be updated with the latest candle(s) before calling
this (see paper_trading/README.md).

Usage:
  python scripts/paper_trade_update.py                                       # daily track (default)
  python scripts/paper_trade_update.py --suffix _15m --freq 15min --tracking-start "2026-08-08 08:45:00"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import pandas as pd

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.metrics import compute_metrics
from src.backtest.strategies import ALL_STRATEGY_CLASSES

CAPITAL = 100_000.0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suffix", default="", help="File suffix distinguishing this track, e.g. '_15m'. Default '' = the original daily track.")
    p.add_argument("--freq", default="1D", help="Pandas freq string for bar resampling/annualization, e.g. '1D', '15min'.")
    p.add_argument("--tracking-start", default="2026-08-08", help="Timestamp (parseable by pandas) marking where the live track record begins.")
    p.add_argument("--symbol", default="BTC_USDT", help="Instrument symbol for backtest spec lookup and metadata, e.g. 'ETH_USDT', 'SOL_USDT'.")
    return p.parse_args(argv)


def _update_track_record(bars, strategy_name, result, capital, tracking_start, track_record_path):
    if tracking_start in bars.index:
        start_idx = bars.index.get_loc(tracking_start)
    else:
        # Tracking start predates the bar history we have, or hasn't arrived
        # yet - fall back to the first bar so we don't crash.
        start_idx = 0

    eq = result.equity_curve
    equity_at_start = eq.iloc[start_idx - 1] if start_idx > 0 else capital
    current_equity = eq.iloc[-1]
    return_since_start = current_equity / equity_at_start - 1 if equity_at_start else 0.0

    latest_bar_key = str(bars.index[-1])
    row = {
        "date": latest_bar_key,
        "strategy": strategy_name,
        "equity": round(current_equity, 2),
        "return_since_tracking_start_pct": round(return_since_start * 100, 3),
        "position": result.positions.iloc[-1],
    }

    if os.path.exists(track_record_path):
        existing = pd.read_csv(track_record_path)
        existing = existing[~((existing["date"] == latest_bar_key) & (existing["strategy"] == strategy_name))]
        updated = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        updated = pd.DataFrame([row])
    updated = updated.sort_values(["date", "strategy"])
    updated.to_csv(track_record_path, index=False)


def main(argv=None):
    args = parse_args(argv)
    bars_path = f"paper_trading/bars{args.suffix}.csv"
    positions_path = f"paper_trading/positions{args.suffix}.json"
    trade_log_path = f"paper_trading/trade_log{args.suffix}.csv"
    track_record_path = f"paper_trading/track_record{args.suffix}.csv"
    summary_path = f"paper_trading/summary{args.suffix}.md"
    tracking_start = pd.Timestamp(args.tracking_start)

    bars = load_bars(bars_path, freq=args.freq)
    spec = get_spec(args.symbol)

    positions = {}
    all_trades = []
    summary_rows = []

    for cls in ALL_STRATEGY_CLASSES:
        strat = cls()
        result = run_backtest(bars, strat, spec, initial_capital=CAPITAL)
        metrics = compute_metrics(result, CAPITAL, freq_hint=args.freq)
        _update_track_record(bars, strat.name, result, CAPITAL, tracking_start, track_record_path)

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

    with open(positions_path, "w") as f:
        json.dump({
            "symbol": args.symbol,
            "freq": args.freq,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "latest_bar": str(bars.index[-1]),
            "bar_count": len(bars),
            "strategies": positions,
        }, f, indent=2)

    pd.DataFrame(all_trades).to_csv(trade_log_path, index=False)

    lines = [
        f"# {args.symbol.replace('_', '/')} Paper Trading ({args.freq}) — updated {datetime.now(timezone.utc).isoformat()}",
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
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Updated {positions_path}, {trade_log_path}, {summary_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
