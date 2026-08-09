"""Snapshot per-strategy parameter sensitivity into a JSON the dashboard can
render directly - the companion question to walk-forward validation. Walk-
forward asks "does this strategy hold up on data it never saw"; sensitivity
asks "is its edge a plateau across nearby parameter choices, or a spike at
exactly one setting that would vanish with a slightly different default" -
the second is a classic overfitting tell even when the first looks fine.

Deliberately not part of the hourly pipeline, same reasoning as
walkforward_snapshot.py: this reruns a full backtest per parameter value per
strategy, expensive next to a single pass. Run manually after data changes
meaningfully.

Usage:
  python scripts/sensitivity_snapshot.py --bars paper_trading/bars.csv --symbol BTC_USDT --freq 1D --output paper_trading/sensitivity.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

sys.path.insert(0, ".")

from src.backtest.data_loader import load_bars
from src.backtest.instruments import get_spec
from src.backtest.sensitivity import param_sensitivity
from src.backtest.strategies import ALL_STRATEGY_CLASSES

# Matches the stop-loss/liquidation floor scripts/paper_trade_update.py
# applies to every live paper-trading track - sweeping parameters without it
# would let a handful of ancient blowup trades (unbounded losses on a wildly
# wrong parameter value) dominate the read on how stable a strategy's edge
# actually is.
MAX_LOSS_FRACTION = 0.5


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bars", required=True, help="Path to a bars CSV (timestamp,open,high,low,close,volume).")
    p.add_argument("--symbol", required=True, help="Instrument symbol for spec lookup, e.g. BTC_USDT.")
    p.add_argument("--freq", default="1D")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--output", required=True)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    bars = load_bars(args.bars, freq=args.freq)
    spec = get_spec(args.symbol)

    results = []
    for cls in ALL_STRATEGY_CLASSES:
        name = cls().name
        print(f"Sensitivity: {name}...")
        try:
            res = param_sensitivity(
                bars, cls, spec, freq_hint=args.freq, initial_capital=args.capital,
                max_loss_fraction=MAX_LOSS_FRACTION,
            )
        except ValueError as e:
            print(f"  skipped: {e}")
            results.append({"strategy": name, "error": str(e)})
            continue
        detail = res.detail
        frac_profitable = float((detail["total_return"] > 0).mean())
        results.append({
            "strategy": name,
            "n_values_tested": int(len(detail)),
            "frac_profitable": frac_profitable,
            "sharpe_min": float(detail["sharpe"].min()),
            "sharpe_max": float(detail["sharpe"].max()),
        })
        print(f"  {frac_profitable*100:.0f}% of {len(detail)} nearby parameter values still profitable")

    out = {
        "symbol": args.symbol,
        "freq": args.freq,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "results": results,
    }
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
