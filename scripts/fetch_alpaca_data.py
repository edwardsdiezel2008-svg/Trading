"""Download real historical bars from Alpaca's free market data API and save
them in the exact CSV shape `load_bars()` already auto-detects - drop the
output straight into data/raw/ and run the CLI, no reformatting needed.

Requires a free Alpaca account (https://alpaca.markets) and API keys set as
environment variables - never pass them on the command line or paste them
into a file that gets committed:

  export ALPACA_API_KEY=...
  export ALPACA_SECRET_KEY=...

Usage:
  python scripts/fetch_alpaca_data.py --symbols AAPL MSFT --start 2024-01-01 --end 2025-01-01 --timeframe 1Min
  python scripts/fetch_alpaca_data.py --symbols AAPL --start 2020-01-01 --end 2025-01-01 --timeframe 1Day

Free-tier data is the IEX feed (one exchange's volume, not the full
consolidated tape) - fine for backtesting, just not literally "every NASDAQ
print." The full SIP feed needs a paid Alpaca subscription (--feed sip).
"""
from __future__ import annotations

import argparse
import os

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

_TIMEFRAME_MAP = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "30Min": TimeFrame(30, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="+", required=True, help="e.g. AAPL MSFT NVDA")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--timeframe", default="1Min", choices=sorted(_TIMEFRAME_MAP.keys()))
    p.add_argument("--feed", default="iex", choices=["iex", "sip"], help="iex = free tier, sip = full tape (paid)")
    p.add_argument("--output-dir", default="data/raw")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise SystemExit(
            "Missing credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY as environment "
            "variables (from the API Keys page in your Alpaca dashboard) before running this script."
        )

    client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    os.makedirs(args.output_dir, exist_ok=True)

    request = StockBarsRequest(
        symbol_or_symbols=args.symbols,
        timeframe=_TIMEFRAME_MAP[args.timeframe],
        start=args.start,
        end=args.end,
        feed=args.feed,
    )
    print(f"Requesting {args.timeframe} bars for {args.symbols} from {args.start} to {args.end} (feed={args.feed})...")
    bar_set = client.get_stock_bars(request)
    df = bar_set.df
    if df.empty:
        raise SystemExit("No bars returned - check the symbol(s), date range, and that your account has access to this feed.")

    for symbol in args.symbols:
        if symbol not in df.index.get_level_values("symbol"):
            print(f"  {symbol}: no data returned, skipping")
            continue
        sub = df.xs(symbol, level="symbol").reset_index()
        sub = sub.rename(columns={"timestamp": "timestamp"})[["timestamp", "open", "high", "low", "close", "volume"]]
        out_path = os.path.join(args.output_dir, f"{symbol}_{args.timeframe}_bars.csv")
        sub.to_csv(out_path, index=False)
        print(f"  {symbol}: wrote {len(sub):,} bars to {out_path}")

    print("\nDone. Load with e.g.:")
    print(f"  python -m src.backtest.cli --data {args.output_dir}/{args.symbols[0]}_{args.timeframe}_bars.csv:{args.symbols[0]} --freq {args.timeframe.replace('Min','min').replace('Hour','h').replace('Day','D')}")


if __name__ == "__main__":
    main()
