"""Snapshot walk-forward out-of-sample robustness per strategy into a JSON
the dashboard can render directly - the question a naive full-period
backtest can't answer: is a strategy's edge real, or did it just get lucky
fitting one long history? Re-optimizes each strategy's parameters per
fold and scores it on data it never saw during that fold's fit.

Deliberately not part of the hourly pipeline - this grid-searches
parameters per fold per strategy, expensive next to a single backtest.
Run manually after data changes meaningfully (e.g. after a deep backfill).

Usage:
  python scripts/walkforward_snapshot.py --bars paper_trading/bars.csv --symbol BTC_USDT --freq 1D --output paper_trading/walkforward.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

sys.path.insert(0, ".")

from scripts.paper_trade_update import perp_max_loss_fraction
from src.backtest.data_loader import load_bars
from src.backtest.instruments import get_spec
from src.backtest.significance import bootstrap_return_ci
from src.backtest.strategies import ALL_STRATEGY_CLASSES
from src.backtest.walkforward import run_walk_forward


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bars", required=True, help="Path to a bars CSV (timestamp,open,high,low,close,volume).")
    p.add_argument("--symbol", required=True, help="Instrument symbol for spec lookup, e.g. BTC_USDT.")
    p.add_argument("--freq", default="1D")
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--leverage", type=float, default=1.0,
                    help="Leverage for a perpetual futures track (sets capital_fraction and the "
                         "maintenance-margin-based liquidation floor, matching paper_trade_update.py).")
    p.add_argument("--output", required=True)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    bars = load_bars(args.bars, freq=args.freq)
    spec = get_spec(args.symbol)
    engine_kwargs = {"capital_fraction": args.leverage}
    if args.leverage != 1.0:
        engine_kwargs["max_loss_fraction"] = perp_max_loss_fraction(args.leverage)

    results = []
    for cls in ALL_STRATEGY_CLASSES:
        name = cls().name
        print(f"Walk-forward: {name}...")
        try:
            wf = run_walk_forward(bars, cls, spec, n_folds=args.n_folds, initial_capital=args.capital, freq_hint=args.freq, **engine_kwargs)
        except ValueError as e:
            print(f"  skipped: {e}")
            results.append({"strategy": name, "error": str(e)})
            continue
        ci = bootstrap_return_ci(wf.oos_equity_curve)
        results.append({
            "strategy": name,
            "oos_total_return": wf.oos_metrics["total_return"],
            "oos_sharpe": wf.oos_metrics["sharpe"],
            "oos_max_drawdown": wf.oos_metrics["max_drawdown"],
            "oos_num_trades": wf.oos_metrics["num_trades"],
            "baseline_total_return": wf.baseline_metrics["total_return"],
            "baseline_sharpe": wf.baseline_metrics["sharpe"],
            "vs_fixed_default_ratio": wf.vs_fixed_default_ratio,
            "n_folds": len(wf.folds),
            "oos_return_ci_low": ci["ci_low"],
            "oos_return_ci_high": ci["ci_high"],
            "oos_return_ci_level": ci["ci_level"],
            "oos_significant": ci["significant"],
        })

    out = {
        "symbol": args.symbol,
        "freq": args.freq,
        "n_folds": args.n_folds,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "results": results,
    }
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.output}")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
