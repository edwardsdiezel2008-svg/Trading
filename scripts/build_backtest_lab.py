"""Build the interactive Backtest Lab page (paper_trading/backtest_lab.html):
a client-side tool where you pick a strategy, a 1-to-5-minute-bar track, a
starting balance, and a drawdown limit, and see a real, bar-level equity
curve with a trailing-drawdown simulation on top - answering "would this
account have survived" for a real, historical run, not a hypothetical one.
It also ranks every run on a Leaderboard tab, so you can see which strategy
and parameter combination actually performed best instead of picking one
blind.

Runs every strategy in the library against its own PARAM_SPACE's full,
real, documented parameter grid - not samples, not invented values - capped
at 50 combinations per strategy (an evenly-spaced thinning of the real grid
only kicks in if a strategy's grid actually exceeds that; today the largest,
RSIReversion, has 36). Each config is backtested against every 1-to-5-minute
track this project actually fetches (NQ 1-min, NQ/ES/YM/RTY/GC/CL 5-min -
there is no other genuine 1-5min bar data available).

Only compact data is shipped to the page: each track's bars as
[epoch_seconds, close] pairs (nothing else needed to reconstruct mark-to-
market equity between trades), and every config's summary metrics (for the
Leaderboard). Full trade lists - the only thing needed to draw an equity
curve - are shipped only for chart-worthy configs (each strategy's
hardcoded defaults and PARAM_SPACE extremes, plus whichever configs land in
the top 10 by total return or top 10 by Sharpe on that track) so the page's
payload stays bounded no matter how many parameter combinations get
backtested. Trade lists are
[entry_idx, exit_idx, direction, entry_price, exit_price, net_pnl] tuples
indexing into that track's bars. The page reconstructs the full per-bar
equity curve and simulates the trailing-drawdown breach with pure
arithmetic over these real numbers - no strategy logic is duplicated in
JavaScript, so there's no way for the two to drift apart.

Usage: python scripts/build_backtest_lab.py
"""
from __future__ import annotations

import datetime
import itertools
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
MAX_CONFIGS_PER_STRATEGY = 50
CHART_TOP_N = 10  # per track, per ranking metric (total return, then Sharpe)

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
    """Every real, distinct config worth backtesting per strategy class: its
    hardcoded defaults (empty params dict) plus every combination in its own
    PARAM_SPACE - not samples, not invented values, only what this project's
    own sensitivity sweeps already exercise. Capped at MAX_CONFIGS_PER_STRATEGY
    combos per strategy via even thinning across the real grid if it's ever
    larger than that (none currently are)."""
    configs = []
    for cls in ALL_STRATEGY_CLASSES:
        configs.append((cls, {}))
        space = cls.PARAM_SPACE
        if not space:
            continue
        keys = list(space.keys())
        grid = list(itertools.product(*(space[k] for k in keys)))
        budget = MAX_CONFIGS_PER_STRATEGY - 1
        if len(grid) > budget:
            idxs = sorted({round(i * (len(grid) - 1) / (budget - 1)) for i in range(budget)})
            grid = [grid[i] for i in idxs]
        configs.extend((cls, dict(zip(keys, combo))) for combo in grid)
    return configs


def _param_extremes(cls):
    """The most conservative combo (every param at its list's first value)
    and most aggressive combo (every param at its last value) - the same two
    configs the lab always guaranteed a chart for before the full grid was
    added, so every strategy keeps at least these charts regardless of how
    it ranks."""
    space = cls.PARAM_SPACE
    if not space:
        return {}, {}
    return {k: v[0] for k, v in space.items()}, {k: v[-1] for k, v in space.items()}


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


def _select_chart_ids(computed, top_n=CHART_TOP_N):
    """Which of a track's computed configs get their trade list shipped
    (chartable): each strategy's hardcoded defaults/PARAM_SPACE extremes
    (`_is_extreme`), plus whichever configs land in the top `top_n` by total
    return or top `top_n` by Sharpe. `computed` is a list of dicts each with
    `total_return`, `sharpe`, and `_is_extreme` keys (None metrics are
    excluded from ranking, not treated as worst). Returns a set of the
    qualifying dicts' id()s - the caller still owns the objects, this only
    decides which ones qualify."""
    by_return = sorted(
        (c for c in computed if c["total_return"] is not None),
        key=lambda c: c["total_return"], reverse=True,
    )[:top_n]
    by_sharpe = sorted(
        (c for c in computed if c["sharpe"] is not None),
        key=lambda c: c["sharpe"], reverse=True,
    )[:top_n]
    return {id(c) for c in by_return} | {id(c) for c in by_sharpe} | {
        id(c) for c in computed if c["_is_extreme"]
    }


def main():
    configs = strategy_configs()
    extremes = {cls: _param_extremes(cls) for cls in ALL_STRATEGY_CLASSES}
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

        # Run every config once, keeping its real Trade objects in memory -
        # which ones get a full chart (trades serialized into the payload)
        # is decided only after every config's metrics are known, so the
        # decision can be "the best ones", not "however many fit".
        computed = []
        seen_names = set()
        for cls, params in configs:
            strat = cls(params=params)
            if strat.name in seen_names:
                # A grid combo resolved to the exact same params as an
                # earlier entry (e.g. the class's hardcoded defaults are
                # also a point on its own PARAM_SPACE grid) - same trades,
                # skip the redundant backtest and duplicate leaderboard row.
                continue
            seen_names.add(strat.name)
            lo, hi = extremes[cls]
            result = run_backtest(bars, strat, spec, initial_capital=CAPITAL)
            m = compute_metrics(result, initial_capital=CAPITAL, freq_hint=freq)
            computed.append({
                "name": strat.name,
                "base": cls.__name__,
                "total_return": _safe_num(m["total_return"]),
                "sharpe": _safe_num(m["sharpe"], 3),
                "max_drawdown": _safe_num(m["max_drawdown"]),
                "num_trades": m["num_trades"],
                "win_rate": _safe_num(m["win_rate"], 4),
                "profit_factor": _safe_num(m["profit_factor"], 3),
                "_trades": result.trades,
                "_is_extreme": params in ({}, lo, hi),
            })

        chart_ids = _select_chart_ids(computed)

        strat_list = []
        for c in computed:
            entry = {k: v for k, v in c.items() if not k.startswith("_")}
            if id(c) in chart_ids:
                entry["trades"] = _trades_json(c["_trades"], bars.index)
            strat_list.append(entry)
        out["strategies"][key] = strat_list

        n_trades = sum(len(s.get("trades", [])) for s in strat_list)
        n_charted = sum(1 for s in strat_list if "trades" in s)
        print(f"  {label}: {len(bars)} bars, {len(strat_list)} configs ({n_charted} chartable), {n_trades} total trades")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    import os
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
