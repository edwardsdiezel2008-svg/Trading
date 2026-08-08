"""Run walk-forward validation and parameter sensitivity sweeps across the
strategy library, for a given instrument's data. This is separate from the
main CLI (`src/backtest/cli.py`) because grid-searching parameters per fold
is much more expensive than a single backtest - run it when you actually
want to know whether a strategy's edge is real, not on every iteration.

Usage:
  python scripts/run_validation.py --data data/sample/NASDAQ_AAPL_ticks.csv:AAPL --freq 5min
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, ".")

import pandas as pd

from src.backtest.data_loader import load_bars
from src.backtest.instruments import get_spec
from src.backtest.sensitivity import param_sensitivity
from src.backtest.strategies import ALL_STRATEGY_CLASSES
from src.backtest.walkforward import run_walk_forward


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, help="'path:SYMBOL' pair, e.g. data/sample/NASDAQ_AAPL_ticks.csv:AAPL")
    p.add_argument("--freq", default="5min")
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--output", default="reports/validation")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    path, symbol = args.data.rsplit(":", 1)
    bars = load_bars(path, freq=args.freq)
    spec = get_spec(symbol.upper())
    os.makedirs(args.output, exist_ok=True)

    wf_summary_rows, wf_fold_rows = [], []
    sens_summary_rows, sens_detail_rows = [], []

    for cls in ALL_STRATEGY_CLASSES:
        name = cls.__name__
        print(f"Walk-forward: {name}...")
        try:
            wf = run_walk_forward(bars, cls, spec, n_folds=args.n_folds, initial_capital=args.capital, freq_hint=args.freq)
        except ValueError as e:
            print(f"  skipped: {e}")
            wf = None

        if wf is not None:
            wf_summary_rows.append({
                "strategy": name,
                "oos_total_return": wf.oos_metrics["total_return"],
                "oos_sharpe": wf.oos_metrics["sharpe"],
                "oos_max_drawdown": wf.oos_metrics["max_drawdown"],
                "oos_num_trades": wf.oos_metrics["num_trades"],
                "baseline_total_return": wf.baseline_metrics["total_return"],
                "baseline_sharpe": wf.baseline_metrics["sharpe"],
                "vs_fixed_default_ratio": wf.vs_fixed_default_ratio,
                "n_folds": len(wf.folds),
            })
            for f in wf.folds:
                wf_fold_rows.append({
                    "strategy": name, "fold": f.fold_idx,
                    "train_start": f.train_start, "train_end": f.train_end,
                    "test_start": f.test_start, "test_end": f.test_end,
                    "chosen_params": f.chosen_params, "train_score": f.train_score,
                    "test_total_return": f.test_metrics["total_return"],
                    "test_sharpe": f.test_metrics["sharpe"],
                    "test_num_trades": f.test_metrics["num_trades"],
                })

        print(f"Sensitivity: {name}...")
        sens = param_sensitivity(bars, cls, spec, initial_capital=args.capital, freq_hint=args.freq)
        for pname, row in sens.summary.iterrows():
            sens_summary_rows.append({"strategy": name, "parameter": pname, **row.to_dict()})
        for _, row in sens.detail.iterrows():
            sens_detail_rows.append({"strategy": name, **row.to_dict()})

    pd.DataFrame(wf_summary_rows).to_csv(os.path.join(args.output, "walkforward_summary.csv"), index=False)
    pd.DataFrame(wf_fold_rows).to_csv(os.path.join(args.output, "walkforward_folds.csv"), index=False)
    pd.DataFrame(sens_summary_rows).to_csv(os.path.join(args.output, "sensitivity_summary.csv"), index=False)
    pd.DataFrame(sens_detail_rows).to_csv(os.path.join(args.output, "sensitivity_detail.csv"), index=False)

    print(f"\nWrote walkforward_summary.csv, walkforward_folds.csv, sensitivity_summary.csv, sensitivity_detail.csv to {args.output}/")
    if wf_summary_rows:
        print("\nWalk-forward summary (out-of-sample):")
        print(pd.DataFrame(wf_summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
