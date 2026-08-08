"""Run the full strategy library against the sample data and export a compact
JSON blob for the interactive replay artifact: bars, regimes, and per-strategy
positions/equity/trades.

Usage: python scripts/export_replay_data.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.regime import classify_regimes
from src.backtest.metrics import compute_metrics
from src.backtest.strategies import build_default_strategies

CAPITAL = 100_000.0


def export_instrument(symbol: str, path: str, freq: str = "5min") -> dict:
    bars = load_bars(path, freq=freq)
    spec = get_spec(symbol)
    regimes = classify_regimes(bars)
    strategies = build_default_strategies()

    bars_out = {
        "t": [int(ts.timestamp()) for ts in bars.index],
        "o": [round(v, 4) for v in bars["open"]],
        "h": [round(v, 4) for v in bars["high"]],
        "l": [round(v, 4) for v in bars["low"]],
        "c": [round(v, 4) for v in bars["close"]],
    }
    regime_out = {
        "trend": [None if pd_isna(v) else v for v in regimes["trend_regime"]],
        "vol": [None if pd_isna(v) else v for v in regimes["vol_regime"]],
    }

    strategies_out = []
    for strat in strategies:
        result = run_backtest(bars, strat, spec, initial_capital=CAPITAL)
        metrics = compute_metrics(result, CAPITAL, freq_hint=freq)
        strategies_out.append({
            "name": strat.name,
            "positions": [int(p) for p in result.positions],
            "equity": [round(v, 2) for v in result.equity_curve],
            "trades": [
                {
                    "entry_t": int(t.entry_time.timestamp()),
                    "exit_t": int(t.exit_time.timestamp()),
                    "dir": t.direction,
                    "entry_px": round(t.entry_price, 4),
                    "exit_px": round(t.exit_price, 4),
                    "net_pnl": round(t.net_pnl, 2),
                }
                for t in result.trades
            ],
            "metrics": {
                "total_return": metrics["total_return"],
                "sharpe": metrics["sharpe"],
                "max_drawdown": metrics["max_drawdown"],
                "win_rate": metrics["win_rate"],
                "num_trades": metrics["num_trades"],
            },
        })

    return {
        "symbol": symbol,
        "freq": freq,
        "initial_capital": CAPITAL,
        "bars": bars_out,
        "regimes": regime_out,
        "strategies": strategies_out,
    }


def pd_isna(v):
    import pandas as pd
    return pd.isna(v)


def main():
    data = {
        "instruments": [
            export_instrument("BTC_USDT", "data/raw/BTC_USDT_1D_bars.csv", freq="1D"),
            export_instrument("AAPL", "data/sample/NASDAQ_AAPL_ticks.csv", freq="5min"),
            export_instrument("ES", "data/sample/ES_ticks.csv", freq="5min"),
        ]
    }
    out_path = "/tmp/claude-0/-home-user-Trading/381d606c-177e-5630-98bb-7e86b3d62d32/scratchpad/replay_data.json"
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / 1e6
    print(f"Wrote {out_path} ({size_mb:.2f} MB)")
    for inst in data["instruments"]:
        print(f"  {inst['symbol']}: {len(inst['bars']['t']):,} bars, {len(inst['strategies'])} strategies")


if __name__ == "__main__":
    main()
