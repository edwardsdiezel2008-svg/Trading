"""Download historical candlesticks from Crypto.com Exchange's public market
data API and save them in the exact CSV shape `load_bars()` already
auto-detects. No account or API key needed - candlestick data is public.

CAVEAT: this hits Crypto.com's documented REST shape
(GET https://api.crypto.com/exchange/v1/public/get-candlestick) but has not
been exercised against a live response - build/test environments for this
tool don't have network access to verify it end-to-end. Run it once, check
the printed row count and a `head` of the output CSV look sane, and if the
API rejects a param or the JSON shape doesn't match, paste the error/response
back and this can be fixed against ground truth instead of documentation.

The public endpoint returns only the most recent `--count` candles per call
(no documented start/end pagination as of writing) - fine for a few hundred/
thousand recent bars, not a deep multi-year backfill. If you need more
history than one call covers, check Crypto.com's API docs for pagination
support and this script can be extended.

Usage:
  python scripts/fetch_cryptocom_data.py --instrument BTC_USDT --timeframe 1D --count 300
  python scripts/fetch_cryptocom_data.py --instrument BTC_USDT --timeframe 1h --count 1000
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
import requests

API_URL = "https://api.crypto.com/exchange/v1/public/get-candlestick"

_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "12h", "1D", "7D", "14D", "1M"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instrument", default="BTC_USDT", help="e.g. BTC_USDT, BTC_USD")
    p.add_argument("--timeframe", default="1D", choices=_TIMEFRAMES)
    p.add_argument("--count", type=int, default=300, help="most recent N candles (API-side cap applies, exact limit unconfirmed)")
    p.add_argument("--output-dir", default="data/raw")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Requesting {args.count} x {args.timeframe} candles for {args.instrument}...")
    try:
        resp = requests.get(
            API_URL,
            params={"instrument_name": args.instrument, "timeframe": args.timeframe, "count": args.count},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        raise SystemExit(f"Request to Crypto.com failed: {e}") from e

    if payload.get("code") not in (0, None):
        raise SystemExit(f"Crypto.com API returned an error payload: {payload}")

    try:
        candles = payload["result"]["data"]
    except (KeyError, TypeError) as e:
        raise SystemExit(
            f"Unexpected response shape (expected result.data): {payload}\n"
            f"The documented shape may have changed - paste this output back to fix the parser."
        ) from e

    if not candles:
        raise SystemExit("No candles returned - check the instrument name and timeframe.")

    df = pd.DataFrame(candles)
    df = df.rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.sort_values("timestamp")[["timestamp", "open", "high", "low", "close", "volume"]]

    out_path = os.path.join(args.output_dir, f"{args.instrument}_{args.timeframe}_bars.csv")
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df):,} bars to {out_path}")
    # --freq only matters for raw tick resampling; load_bars() auto-detects this
    # file as already bar-level (has open/high/low/close) and ignores it, so any
    # reasonable value works here - it's just documentation for the reader.
    print(f"\nLoad with e.g.:\n  python -m src.backtest.cli --data {out_path}:{args.instrument} --freq {args.timeframe}")


if __name__ == "__main__":
    main()
