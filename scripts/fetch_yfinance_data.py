"""Download historical bars from Yahoo Finance via `yfinance` - no account,
no API key, nothing to sign up for. Writes CSVs into data/raw/ in the exact
shape `load_bars()` already auto-detects.

Tradeoff vs the Alpaca script: Yahoo's intraday history is short - roughly
the last 7 days for 1-minute bars, ~60 days for other sub-daily intervals.
Daily bars and coarser go back decades. Fine for quick testing or
daily-bar backtests; not a substitute for Alpaca if you want years of
minute-level NASDAQ history.

Usage:
  python scripts/fetch_yfinance_data.py --symbols AAPL MSFT --start 2015-01-01 --end 2025-01-01 --interval 1d
  python scripts/fetch_yfinance_data.py --symbols AAPL --start 2026-08-01 --end 2026-08-08 --interval 1m
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
import yfinance as yf

_INTERVALS = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="+", required=True, help="e.g. AAPL MSFT NVDA")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--interval", default="1d", choices=_INTERVALS)
    p.add_argument("--output-dir", default="data/raw")
    return p.parse_args(argv)


def _fetch_one(symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, interval=interval, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance has returned both flat columns and (field, ticker) MultiIndex
    # columns across versions - collapse to the field level either way.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={ts_col: "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.output_dir, exist_ok=True)

    for symbol in args.symbols:
        print(f"Requesting {args.interval} bars for {symbol} from {args.start} to {args.end}...")
        try:
            df = _fetch_one(symbol, args.start, args.end, args.interval)
        except Exception as e:
            print(f"  {symbol}: request failed ({e}), skipping")
            continue
        if df.empty:
            print(f"  {symbol}: no data returned - check the symbol, date range, and interval history limits (see script docstring)")
            continue
        out_path = os.path.join(args.output_dir, f"{symbol}_{args.interval}_bars.csv")
        df.to_csv(out_path, index=False)
        print(f"  {symbol}: wrote {len(df):,} bars to {out_path}")

    # --freq only matters for raw tick resampling; load_bars() auto-detects this
    # file as already bar-level and ignores it, so any reasonable value works.
    print("\nLoad with e.g.:")
    print(f"  python -m src.backtest.cli --data {args.output_dir}/{args.symbols[0]}_{args.interval}_bars.csv:{args.symbols[0]} --freq {args.interval}")


if __name__ == "__main__":
    main()
