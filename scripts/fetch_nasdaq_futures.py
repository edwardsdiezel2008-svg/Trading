"""Fetch real CME Nasdaq-100 E-mini futures (NQ=F, continuous front contract)
daily and 5-minute bars from Yahoo Finance's public chart endpoint, via the
`yfinance` library (already a project dependency).

Why this instead of the QQQ-ETF-proxy approach tried first: that used
Stooq's per-symbol CSV endpoint, which turned out to return a plain 404 for
`qqq.us` in production (caught via a live GitHub Actions run, not locally -
this sandbox can't reach Stooq to have found that in advance). Rather than
patch a broken proxy source, this switches to Yahoo's `v8/finance/chart`
endpoint, which is unauthenticated, keyless, and - unlike Stooq - serves the
real NQ=F futures continuous-contract series directly, at both daily and
5-minute granularity. That's a strict upgrade over QQQ: real futures prices
instead of an ETF that merely tracks the same index, paired with the real
MNQ (Micro E-mini Nasdaq-100) contract's point-value economics
(InstrumentSpec in src/backtest/instruments.py: $2/point multiplier, $0.75
commission/side) instead of ETF share economics.

Two limitations, both from Yahoo's retention policy, not this script:
- 5-minute bars: only the trailing ~60 days are available per request. This
  script merges into the existing CSV each run (paper_trading/bars_nq5m.csv)
  so history accumulates hourly going forward past that 60-day window, the
  same pattern already used for every other track here.
- Daily bars: NQ=F's continuous-contract series on Yahoo only goes back a
  few years (much shorter than BTC's multi-year history), since it's a
  rolled/spliced series across quarterly contract expirations, not a single
  continuously-traded instrument like a spot crypto pair.
"""
from __future__ import annotations

import datetime
import sys
import time

sys.path.insert(0, ".")

from scripts.fetch_market_data import merge_bars_csv

FUTURES_SYMBOL = "NQ=F"
DAILY_BARS_PATH = "paper_trading/bars_nq.csv"
FIVE_MIN_BARS_PATH = "paper_trading/bars_nq5m.csv"


def _fetch_history(symbol: str, period: str, interval: str, retries: int = 3):
    import yfinance as yf

    last_err = None
    for attempt in range(retries):
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
            if df is not None and not df.empty:
                return df
            last_err = "empty response"
        except Exception as exc:  # yfinance raises a mix of requests/JSON errors
            last_err = exc
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {symbol} ({interval}) after {retries} attempts: {last_err}")


def _df_to_candles(df) -> list[dict]:
    candles = []
    for ts, row in df.iterrows():
        dt = ts.to_pydatetime()
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        candles.append({
            "timestamp": dt.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]) if row["Volume"] == row["Volume"] else 0.0,  # NaN check
        })
    return candles


def main():
    wrote_any = False

    try:
        daily_df = _fetch_history(FUTURES_SYMBOL, period="10y", interval="1d")
        n = merge_bars_csv(DAILY_BARS_PATH, _df_to_candles(daily_df), date_only=True)
        print(f"{DAILY_BARS_PATH}: {n} rows ({len(daily_df)} fetched this run)")
        wrote_any = True
    except Exception as exc:
        print(f"WARN daily NQ=F fetch failed this run - {exc}")

    try:
        intraday_df = _fetch_history(FUTURES_SYMBOL, period="60d", interval="5m")
        n = merge_bars_csv(FIVE_MIN_BARS_PATH, _df_to_candles(intraday_df), date_only=False)
        print(f"{FIVE_MIN_BARS_PATH}: {n} rows ({len(intraday_df)} fetched this run)")
        wrote_any = True
    except Exception as exc:
        print(f"WARN 5-minute NQ=F fetch failed this run - {exc}")

    if not wrote_any:
        raise SystemExit("Both NQ=F fetches failed this run - no data written")


if __name__ == "__main__":
    main()
