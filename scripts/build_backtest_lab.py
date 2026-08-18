"""Build the interactive Backtest Lab page (paper_trading/backtest_lab.html):
a client-side tool where you pick a strategy, a 1-to-5-minute-bar track, a
starting balance, and a drawdown limit, and see a real, bar-level equity
curve with a trailing-drawdown simulation on top - answering "would this
account have survived" for a real, historical run, not a hypothetical one.

Runs every strategy in the library against every parameter configuration in
its own PARAM_SPACE at the extremes (its hardcoded defaults, plus its most
conservative and most aggressive documented combo) - 18 strategies x 3
configs = 54, all real, already-vetted values, nothing invented to hit a
round number. Each config is backtested against every 1-to-5-minute track
this project actually fetches (NQ 1-min, NQ/ES/YM/RTY/GC/CL 5-min - there is
no other genuine 1-5min bar data available), 378 backtests total.

Only compact data is shipped to the page: each track's bars as
[epoch_seconds, close] pairs (nothing else needed to reconstruct mark-to-
market equity between trades), and each strategy's real trade list as
[entry_idx, exit_idx, direction, entry_price, exit_price, net_pnl] tuples
indexing into that track's bars. The page reconstructs the full per-bar
equity curve and simulates the trailing-drawdown breach with pure
arithmetic over these real numbers - no strategy logic is duplicated in
JavaScript, so there's no way for the two to drift apart.

Usage: python scripts/build_backtest_lab.py
"""
from __future__ import annotations

import datetime
import json
import sys

sys.path.insert(0, ".")

import numpy as np

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.metrics import compute_metrics
from src.backtest.strategies import ALL_STRATEGY_CLASSES

OUTPUT_PATH = "paper_trading/backtest_lab.json"
CAPITAL = 100_000.0

# (key, label, bars path, symbol, freq hint) - every track this project
# fetches at 1-5 minute resolution. NQ is the only 1-minute series; the
# other five index/commodity futures only have 5-minute bars.
TRACKS = [
    ("nq_1m", "Nasdaq Futures (1-min)", "paper_trading/bars_nq1m.csv", "MNQ", "1min"),
    ("nq_5m", "Nasdaq Futures (5-min)", "paper_trading/bars_nq5m.csv", "MNQ", "5min"),
    ("es_5m", "S&P 500 Futures (5-min)", "paper_trading/bars_es5m.csv", "MES", "5min"),
    ("ym_5m", "Dow Futures (5-min)", "paper_trading/bars_ym5m.csv", "MYM", "5min"),
    ("rty_5m", "Russell 2000 Futures (5-min)", "paper_trading/bars_rty5m.csv", "M2K", "5min"),
    ("gc_5m", "Gold Futures (5-min)", "paper_trading/bars_gc5m.csv", "MGC", "5min"),
    ("cl_5m", "Crude Oil Futures (5-min)", "paper_trading/bars_cl5m.csv", "MCL", "5min"),
]


def strategy_configs():
    """3 real, distinct configs per strategy class: its hardcoded defaults
    (empty params dict), plus its PARAM_SPACE's most conservative combo (all
    params at their list's first value) and most aggressive combo (all at
    the last value). Every value here is one this project's own sensitivity
    sweeps already exercise - nothing new is invented just to inflate the
    count. 18 strategies x 3 configs = 54."""
    configs = []
    for cls in ALL_STRATEGY_CLASSES:
        configs.append((cls, {}))
        space = cls.PARAM_SPACE
        if space:
            lo = {k: v[0] for k, v in space.items()}
            hi = {k: v[-1] for k, v in space.items()}
            configs.append((cls, lo))
            if hi != lo:
                configs.append((cls, hi))
    return configs


def _safe_num(v, decimals=4):
    """None for NaN/inf (JSON has no such literal JS can parse) rather than
    writing an invalid token or a silently-misleading huge number."""
    if v is None:
        return None
    f = float(v)
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, decimals)


def _bars_json(bars):
    # [epoch_seconds, close] only - entry/exit prices travel with each trade
    # below, so nothing else is needed to mark a position to market between
    # bars. Cuts the payload by roughly 3x versus full OHLCV.
    #
    # bars.index's underlying unit isn't guaranteed to be nanoseconds (pandas
    # 2.x+ can produce datetime64[us] or [s] depending on how it was built) -
    # casting to datetime64[ns] first before viewing as int64 normalizes
    # that so the //1e9 division is always seconds, not off by a unit factor.
    idx = bars.index.astype("datetime64[ns]").view("int64") // 1_000_000_000
    close = bars["close"].to_numpy()
    return [[int(t), round(float(c), 4)] for t, c in zip(idx, close)]


def _trades_json(trades, bars_index):
    loc = {ts: i for i, ts in enumerate(bars_index)}
    out = []
    for t in trades:
        out.append([
            loc[t.entry_time], loc[t.exit_time], int(t.direction),
            round(float(t.entry_price), 4), round(float(t.exit_price), 4),
            round(float(t.net_pnl), 2),
        ])
    return out


def main():
    configs = strategy_configs()
    print(f"{len(configs)} strategy configurations x {len(TRACKS)} tracks = {len(configs) * len(TRACKS)} backtests")

    out = {
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "tracks": {},
        "strategies": {},
    }
    for key, label, path, symbol, freq in TRACKS:
        bars = load_bars(path, freq=freq)
        spec = get_spec(symbol)
        out["tracks"][key] = {
            "label": label, "symbol": symbol, "freq": freq,
            "multiplier": spec.multiplier, "tick_size": spec.tick_size,
            "bars": _bars_json(bars),
        }

        strat_list = []
        for cls, params in configs:
            strat = cls(params=params)
            result = run_backtest(bars, strat, spec, initial_capital=CAPITAL)
            m = compute_metrics(result, initial_capital=CAPITAL, freq_hint=freq)
            strat_list.append({
                "name": strat.name,
                "base": cls.__name__,
                "total_return": _safe_num(m["total_return"]),
                "sharpe": _safe_num(m["sharpe"], 3),
                "max_drawdown": _safe_num(m["max_drawdown"]),
                "num_trades": m["num_trades"],
                "win_rate": _safe_num(m["win_rate"], 4),
                "profit_factor": _safe_num(m["profit_factor"], 3),
                "trades": _trades_json(result.trades, bars.index),
            })
        out["strategies"][key] = strat_list
        n_trades = sum(len(s["trades"]) for s in strat_list)
        print(f"  {label}: {len(bars)} bars, {len(strat_list)} strategies, {n_trades} total trades")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    import os
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
