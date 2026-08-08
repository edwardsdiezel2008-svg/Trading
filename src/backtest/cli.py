"""Command-line entry point.

Examples:
  python -m src.backtest.cli --data data/sample/NASDAQ_AAPL_ticks.csv:AAPL --freq 1min
  python -m src.backtest.cli --data data/raw/ES_ticks.csv:ES data/raw/AAPL_ticks.csv:AAPL --freq 5min
"""
from __future__ import annotations

import argparse

from .data_loader import load_bars
from .report import run_comparison


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Backtest a library of common strategies over downloaded trading logs.")
    parser.add_argument(
        "--data", nargs="+", required=True,
        help="One or more 'path:SYMBOL' pairs, e.g. data/raw/ES_ticks.csv:ES. "
             "SYMBOL is used to look up instrument specs (contract multiplier etc.).",
    )
    parser.add_argument("--freq", default="1min", help="Bar frequency to resample ticks to (e.g. 1min, 5min, 1h, 1D). Ignored if the file is already bar-level.")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Starting capital per strategy/instrument run.")
    parser.add_argument("--output", default="reports", help="Directory to write metrics.csv, equity_curves.png, explanations.txt.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    bars_by_symbol = {}
    for entry in args.data:
        if ":" not in entry:
            raise SystemExit(f"--data entries must be 'path:SYMBOL', got: {entry}")
        path, symbol = entry.rsplit(":", 1)
        bars_by_symbol[symbol.upper()] = load_bars(path, freq=args.freq)

    result = run_comparison(bars_by_symbol, initial_capital=args.capital, freq_hint=args.freq, output_dir=args.output)

    print(result["metrics"].to_string(index=False))
    print(f"\nFull report written to {args.output}/ (metrics.csv, equity_curves.png, explanations.txt)")


if __name__ == "__main__":
    main()
