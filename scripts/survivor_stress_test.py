"""Stress-test the strategy-track combinations that survived the bootstrap
significance check (see "Statistical significance" in paper_trading/README.md)
- out of 240 strategy-track results, only 5 have a 90% confidence interval
that excludes zero. That's necessary but not sufficient for real confidence:
a single positive-and-significant walk-forward result could still be one
lucky fold, or an edge that evaporates under slightly worse execution
assumptions, or one that only exists in a narrow slice of history. This runs
three additional checks per survivor, none of which the walk-forward
snapshot alone answers:

1. Fold-by-fold consistency - is the OOS edge spread across multiple
   independent test periods, or is one fold carrying the whole result?
2. Cost stress test - re-run the full walk-forward (fresh grid search) at
   3x the normal slippage assumption. If the bootstrap CI no longer
   excludes zero, the edge was thin enough that realistic execution
   friction alone could erase it.
3. Regime concentration - attribute the full-backtest P&L to ADX-based
   trend/volatility regimes. A profit concentrated in one regime bucket is
   a narrower, more fragile edge than one spread across conditions.

Deliberately a one-off analysis script, not part of the hourly pipeline or
even the regular walk-forward/sensitivity snapshot cadence - re-run manually
whenever the "5 survivors" list changes (e.g. after adding more instruments
or after fresh data shifts which strategies clear the bar).

Usage:
  python scripts/survivor_stress_test.py --output paper_trading/survivor_stress_test.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

sys.path.insert(0, ".")

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.regime import attribute_performance, classify_regimes
from src.backtest.significance import bootstrap_return_ci
from src.backtest.strategies.mean_reversion import RSIReversion
from src.backtest.strategies.trend import DonchianBreakout, MovingAverageCrossover
from src.backtest.walkforward import run_walk_forward

# (label, bars path, symbol, freq, strategy class) - all five use their
# strategy's default parameters, which is what the walk-forward baseline
# and the dashboard's Locked-in Strategy full-backtest figure both use too.
SURVIVORS = [
    ("Nasdaq Futures (Daily)", "paper_trading/bars_nq.csv", "MNQ", "1D", RSIReversion),
    ("S&P 500 Futures (Daily)", "paper_trading/bars_es.csv", "MES", "1D", RSIReversion),
    ("Dow Futures (Daily)", "paper_trading/bars_ym.csv", "MYM", "1D", RSIReversion),
    ("Gold Futures (Daily)", "paper_trading/bars_gc.csv", "MGC", "1D", MovingAverageCrossover),
    ("Gold Futures (Daily)", "paper_trading/bars_gc.csv", "MGC", "1D", DonchianBreakout),
]


def run_one(label, bars_path, symbol, freq, strategy_cls):
    bars = load_bars(bars_path, freq=freq)
    spec = get_spec(symbol)
    name = strategy_cls().name

    # 1. Normal-cost walk-forward, for fold-by-fold breakdown.
    wf = run_walk_forward(bars, strategy_cls, spec, freq_hint=freq)
    fold_returns = [
        {
            "fold": f.fold_idx,
            "test_start": str(f.test_start.date()),
            "test_end": str(f.test_end.date()),
            "test_return": f.test_metrics.get("total_return"),
            "test_sharpe": f.test_metrics.get("sharpe"),
        }
        for f in wf.folds
    ]
    folds_positive = sum(1 for f in fold_returns if (f["test_return"] or 0) > 0)

    # 2. Cost-stress: same grid search, 3x slippage_ticks (default is 1.0).
    wf_stressed = run_walk_forward(bars, strategy_cls, spec, freq_hint=freq, slippage_ticks=3.0)
    ci_normal = bootstrap_return_ci(wf.oos_equity_curve)
    ci_stressed = bootstrap_return_ci(wf_stressed.oos_equity_curve)

    # 3. Regime concentration on the full-history default-params backtest.
    full_result = run_backtest(bars, strategy_cls(), spec)
    regimes = classify_regimes(bars)
    attribution = attribute_performance(full_result, regimes)
    regime_breakdown = [
        {
            "regime": idx,
            "total_pnl": float(row["total_pnl"]),
            "pct_of_total_pnl": None if pd_isna(row["pct_of_total_pnl"]) else float(row["pct_of_total_pnl"]),
            "bar_count": int(row["bar_count"]),
        }
        for idx, row in attribution.iterrows()
    ]
    top_regime_pct = regime_breakdown[0]["pct_of_total_pnl"] if regime_breakdown else None

    return {
        "label": label,
        "symbol": symbol,
        "freq": freq,
        "strategy": name,
        "n_folds": len(fold_returns),
        "folds_positive": folds_positive,
        "fold_returns": fold_returns,
        "normal_oos_return": wf.oos_metrics["total_return"],
        "normal_ci_low": ci_normal["ci_low"],
        "normal_ci_high": ci_normal["ci_high"],
        "normal_significant": ci_normal["significant"],
        "stressed_oos_return": wf_stressed.oos_metrics["total_return"],
        "stressed_ci_low": ci_stressed["ci_low"],
        "stressed_ci_high": ci_stressed["ci_high"],
        "stressed_significant": ci_stressed["significant"],
        "survives_cost_stress": bool(ci_stressed["significant"]),
        "regime_breakdown": regime_breakdown,
        "top_regime_pct_of_pnl": top_regime_pct,
    }


def pd_isna(v):
    return v != v  # NaN check without importing pandas at module scope for this alone


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)

    results = []
    for label, bars_path, symbol, freq, strategy_cls in SURVIVORS:
        name = strategy_cls().name
        print(f"Stress-testing {name} on {label}...")
        r = run_one(label, bars_path, symbol, freq, strategy_cls)
        results.append(r)
        print(f"  folds positive: {r['folds_positive']}/{r['n_folds']}")
        print(f"  normal: {r['normal_oos_return']*100:.1f}% OOS, significant={r['normal_significant']}")
        print(f"  3x-slippage: {r['stressed_oos_return']*100:.1f}% OOS, significant={r['stressed_significant']}")
        print(f"  top regime share of P&L: {r['top_regime_pct_of_pnl']}")

    out = {
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "results": results,
    }
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
