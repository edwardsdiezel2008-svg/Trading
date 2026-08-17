"""Stress-test the strategy-track combinations that survived the bootstrap
significance check (see "Statistical significance" in paper_trading/README.md)
- out of 360 strategy-track results (18 strategies x 20 tracks), only 10 have
a 90% confidence interval that excludes zero. That's necessary but not
sufficient for real confidence:
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

Plus one cross-survivor question none of the per-track checks above can
answer alone: does combining the survivors into an equal-weighted portfolio
actually diversify anything, or are they all just riding the same
underlying risk factor? Answered by aligning their OOS equity curves on a
common date intersection, computing pairwise return correlation, and
bootstrapping a confidence interval on the combined portfolio the same way
each individual survivor was checked - directly comparable to the average
of the individual survivors. Only survivors sharing the same bar frequency
go into this step (a daily OOS curve and a 5-minute one share no common
timestamps to align on), so a mixed-frequency survivor list restricts the
portfolio combination to whichever frequency has the most survivors.

Deliberately a one-off analysis script, not part of the hourly pipeline or
even the regular walk-forward/sensitivity snapshot cadence - re-run manually
whenever the survivors list changes (e.g. after adding more instruments,
more strategies, or after fresh data shifts which strategies clear the bar).

Usage:
  python scripts/survivor_stress_test.py --output paper_trading/survivor_stress_test.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.regime import attribute_performance, classify_regimes
from src.backtest.significance import bootstrap_return_ci
from src.backtest.strategies.mean_reversion import CCIReversion, RSIReversion, StochasticReversion, VWAPReversion
from src.backtest.strategies.trend import DonchianBreakout, MovingAverageCrossover
from src.backtest.walkforward import run_walk_forward

# (label, bars path, symbol, freq, strategy class) - all use their
# strategy's default parameters, which is what the walk-forward baseline
# and the dashboard's Locked-in Strategy full-backtest figure both use too.
# Kept in sync with the 90%-CI-excludes-zero results across every
# walkforward_*.json - re-run scripts/walkforward_snapshot.py across all
# tracks and check for new/dropped entries before trusting this list is
# still current (see the module docstring).
SURVIVORS = [
    ("Nasdaq Futures (Daily)", "paper_trading/bars_nq.csv", "MNQ", "1D", RSIReversion),
    ("S&P 500 Futures (Daily)", "paper_trading/bars_es.csv", "MES", "1D", RSIReversion),
    ("Dow Futures (Daily)", "paper_trading/bars_ym.csv", "MYM", "1D", RSIReversion),
    ("Gold Futures (Daily)", "paper_trading/bars_gc.csv", "MGC", "1D", MovingAverageCrossover),
    ("Gold Futures (Daily)", "paper_trading/bars_gc.csv", "MGC", "1D", DonchianBreakout),
    ("Nasdaq Futures (5-Min)", "paper_trading/bars_nq5m.csv", "MNQ", "5min", StochasticReversion),
    ("Russell 2000 Futures (5-Min)", "paper_trading/bars_rty5m.csv", "M2K", "5min", StochasticReversion),
    ("Crude Oil Futures (Daily)", "paper_trading/bars_cl.csv", "MCL", "1D", CCIReversion),
    ("Dow Futures (Daily)", "paper_trading/bars_ym.csv", "MYM", "1D", CCIReversion),
    ("Gold Futures (5-Min)", "paper_trading/bars_gc5m.csv", "MGC", "5min", VWAPReversion),
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

    result = {
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
    return result, wf.oos_equity_curve


def pd_isna(v):
    return v != v  # NaN check without importing pandas at module scope for this alone


def _annualized_sharpe(returns: pd.Series) -> float:
    if len(returns) < 2 or returns.std() == 0:
        return float("nan")
    return float(returns.mean() / returns.std() * np.sqrt(252))


def portfolio_analysis(curves: dict[str, pd.Series]) -> dict:
    """Equal-weighted combination of the survivors' OOS equity curves,
    aligned on their common date intersection (an inner join - each curve
    only has values on its own instrument's trading days, and CME futures
    calendars aren't perfectly identical across index/commodity products).
    """
    returns = {name: eq.pct_change().dropna() for name, eq in curves.items()}
    df = pd.DataFrame(returns).dropna()
    if df.empty or len(df) < 10:
        return {"note": "too few overlapping bars across survivors for a meaningful portfolio analysis"}

    corr = df.corr()
    portfolio_returns = df.mean(axis=1)  # equal-weighted daily return
    portfolio_equity = (1.0 + portfolio_returns).cumprod() * 100_000.0
    portfolio_equity = pd.concat([pd.Series([100_000.0], index=[df.index[0] - pd.Timedelta(days=1)]), portfolio_equity])
    ci = bootstrap_return_ci(portfolio_equity)

    # Recompute each individual's own return/Sharpe restricted to the same
    # aligned window, so "does combining help" compares like with like
    # rather than the portfolio's shorter intersected window against each
    # individual's original, longer, un-intersected OOS window.
    individual_aligned = {}
    for name, r in returns.items():
        r_aligned = r.reindex(df.index).dropna()
        individual_aligned[name] = {
            "total_return": float((1.0 + r_aligned).prod() - 1.0),
            "sharpe": _annualized_sharpe(r_aligned),
        }

    return {
        "aligned_start": str(df.index.min().date()),
        "aligned_end": str(df.index.max().date()),
        "aligned_bar_count": len(df),
        "correlation_matrix": {a: {b: (None if pd_isna(corr.loc[a, b]) else round(float(corr.loc[a, b]), 3)) for b in corr.columns} for a in corr.index},
        "mean_pairwise_correlation": round(float(np.mean([corr.loc[a, b] for i, a in enumerate(corr.index) for b in corr.columns[i + 1:]])), 3) if len(corr) > 1 else None,
        "individual_aligned": individual_aligned,
        "average_individual_return": float(np.mean([v["total_return"] for v in individual_aligned.values()])),
        "average_individual_sharpe": float(np.mean([v["sharpe"] for v in individual_aligned.values()])),
        "portfolio_total_return": float(portfolio_equity.iloc[-1] / 100_000.0 - 1.0),
        "portfolio_sharpe": _annualized_sharpe(portfolio_returns),
        "portfolio_ci_low": ci["ci_low"],
        "portfolio_ci_high": ci["ci_high"],
        "portfolio_significant": ci["significant"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)

    results = []
    curves = {}
    for label, bars_path, symbol, freq, strategy_cls in SURVIVORS:
        name = strategy_cls().name
        print(f"Stress-testing {name} on {label}...")
        r, oos_equity_curve = run_one(label, bars_path, symbol, freq, strategy_cls)
        results.append(r)
        curves[f"{name} / {label}"] = oos_equity_curve
        print(f"  folds positive: {r['folds_positive']}/{r['n_folds']}")
        print(f"  normal: {r['normal_oos_return']*100:.1f}% OOS, significant={r['normal_significant']}")
        print(f"  3x-slippage: {r['stressed_oos_return']*100:.1f}% OOS, significant={r['stressed_significant']}")
        print(f"  top regime share of P&L: {r['top_regime_pct_of_pnl']}")

    # Portfolio combination only makes sense within one bar frequency: a
    # daily OOS equity curve and a 5-minute one never share a timestamp, so
    # an inner join across mixed frequencies degenerates to an empty (or
    # near-empty, calendar-boundary-only) intersection - not a meaningful
    # "does combining diversify anything" answer. Restrict to whichever
    # frequency has the most survivors (currently daily), rather than
    # silently combining series that can't actually be aligned.
    from collections import Counter
    freq_counts = Counter(freq for _, _, _, freq, _ in SURVIVORS)
    portfolio_freq = freq_counts.most_common(1)[0][0]
    portfolio_curves = {
        f"{strategy_cls().name} / {label}": curves[f"{strategy_cls().name} / {label}"]
        for label, _, _, freq, strategy_cls in SURVIVORS
        if freq == portfolio_freq
    }
    print(f"\nCombining the {len(portfolio_curves)} {portfolio_freq} survivors into an equal-weighted portfolio "
          f"({len(SURVIVORS) - len(portfolio_curves)} other-frequency survivor(s) excluded - can't align to a shared calendar)...")
    portfolio = portfolio_analysis(portfolio_curves)
    if "note" in portfolio:
        print(f"  {portfolio['note']}")
    else:
        print(f"  mean pairwise correlation: {portfolio['mean_pairwise_correlation']}")
        print(f"  average individual: {portfolio['average_individual_return']*100:.1f}% return, Sharpe {portfolio['average_individual_sharpe']:.2f}")
        print(f"  portfolio: {portfolio['portfolio_total_return']*100:.1f}% return, Sharpe {portfolio['portfolio_sharpe']:.2f}, significant={portfolio['portfolio_significant']}")

    out = {
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "results": results,
        "portfolio_analysis": portfolio,
    }
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
