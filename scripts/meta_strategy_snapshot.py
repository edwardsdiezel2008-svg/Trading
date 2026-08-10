"""Snapshot the regime-conditional meta-strategy selector's out-of-sample
performance into a JSON the dashboard can render - see
src/backtest/meta_strategy.py for the methodology and its stated limits.

Deliberately not part of the hourly pipeline - it re-backtests every
strategy per fold to learn each regime's best performer, expensive next to
a single backtest, same reasoning as walkforward_snapshot.py. Run manually
after data changes meaningfully.

Usage:
  python scripts/meta_strategy_snapshot.py --bars paper_trading/bars.csv --symbol BTC_USDT --freq 1D --output paper_trading/meta_strategy.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

sys.path.insert(0, ".")

from src.backtest.data_loader import load_bars
from src.backtest.instruments import get_spec
from src.backtest.meta_strategy import run_meta_strategy_walkforward
from src.backtest.regime import classify_regimes
from src.backtest.strategies import ALL_STRATEGY_CLASSES


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bars", required=True, help="Path to a bars CSV (timestamp,open,high,low,close,volume).")
    p.add_argument("--symbol", required=True, help="Instrument symbol for spec lookup, e.g. BTC_USDT.")
    p.add_argument("--freq", default="1D")
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument("--min-regime-bars", type=int, default=20)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--output", required=True)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    bars = load_bars(args.bars, freq=args.freq)
    spec = get_spec(args.symbol)

    print(f"Running meta-strategy walk-forward over {len(bars)} bars, {args.n_folds} folds...")
    try:
        result = run_meta_strategy_walkforward(
            bars, ALL_STRATEGY_CLASSES, spec,
            n_folds=args.n_folds, min_regime_bars=args.min_regime_bars,
            initial_capital=args.capital, freq_hint=args.freq,
        )
    except ValueError as e:
        print(f"Skipped: {e}")
        out = {"symbol": args.symbol, "freq": args.freq, "error": str(e), "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z"}
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2)
        return

    current_regime = classify_regimes(bars)["regime"].iloc[-1]
    current_regime = None if current_regime != current_regime else current_regime  # NaN check
    recommended_strategy = result.live_regime_map.get(current_regime) if current_regime else None

    out = {
        "symbol": args.symbol,
        "freq": args.freq,
        "n_folds": args.n_folds,
        "min_regime_bars": args.min_regime_bars,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "current_regime": current_regime,
        "recommended_strategy": recommended_strategy,
        "live_regime_map": result.live_regime_map,
        "oos_metrics": result.oos_metrics,
        "folds": [
            {
                "fold_idx": f.fold_idx,
                "test_start": str(f.test_start),
                "test_end": str(f.test_end),
                "regime_map": f.regime_map,
                "test_total_return": f.test_metrics.get("total_return"),
                "test_sharpe": f.test_metrics.get("sharpe"),
            }
            for f in result.folds
        ],
    }
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {args.output}")
    print(f"Current regime: {current_regime} -> recommended: {recommended_strategy}")
    print(f"OOS total return: {result.oos_metrics['total_return']:.2%}, Sharpe: {result.oos_metrics['sharpe']:.2f}")


if __name__ == "__main__":
    main()
