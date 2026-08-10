"""Fetch real CME futures (continuous front contracts) daily and 5-minute
bars from Yahoo Finance's public chart endpoint, via the `yfinance` library
(already a project dependency). Despite the module name (kept for history -
it started Nasdaq-only), this now covers CME equity index futures
(Nasdaq-100, S&P 500, Dow, Russell 2000) and commodity futures (Gold, WTI
Crude Oil) too, reusing the exact same fetch/merge logic for every symbol
below rather than duplicating it per-instrument.

Why Yahoo instead of an ETF proxy: an earlier version of the Nasdaq track
traded QQQ against Stooq's per-symbol CSV endpoint, which turned out to
return a plain 404 in production (caught via a live GitHub Actions run, not
locally - this sandbox can't reach Stooq to have found that in advance).
Yahoo's `v8/finance/chart` endpoint is unauthenticated, keyless, and -
unlike Stooq - serves the real futures continuous-contract series directly,
at both daily and 5-minute granularity. That's a strict upgrade over an ETF
proxy: real futures prices, paired with the real Micro E-mini contract's
point-value economics (InstrumentSpec in src/backtest/instruments.py)
instead of ETF share economics.

Two limitations per symbol, both from Yahoo's retention policy, not this
script:
- 5-minute bars: only the trailing ~60 days are available per request. This
  script merges into the existing CSV each run so history accumulates
  hourly going forward past that 60-day window, the same pattern already
  used for every other track here.
- Daily bars: a continuous-contract series on Yahoo only goes back a few
  years (much shorter than BTC's multi-year history), since it's a
  rolled/spliced series across quarterly contract expirations, not a single
  continuously-traded instrument like a spot crypto pair.
"""
from __future__ import annotations

import datetime
import sys
import time

sys.path.insert(0, ".")

from scripts.fetch_market_data import merge_bars_csv

# (Yahoo ticker, daily bars path, 5-minute bars path, label for log lines)
INDEX_FUTURES = [
    ("NQ=F", "paper_trading/bars_nq.csv", "paper_trading/bars_nq5m.csv", "Nasdaq-100 (NQ=F)"),
    ("ES=F", "paper_trading/bars_es.csv", "paper_trading/bars_es5m.csv", "S&P 500 (ES=F)"),
    ("YM=F", "paper_trading/bars_ym.csv", "paper_trading/bars_ym5m.csv", "Dow (YM=F)"),
    ("GC=F", "paper_trading/bars_gc.csv", "paper_trading/bars_gc5m.csv", "Gold (GC=F)"),
    ("RTY=F", "paper_trading/bars_rty.csv", "paper_trading/bars_rty5m.csv", "Russell 2000 (RTY=F)"),
    ("CL=F", "paper_trading/bars_cl.csv", "paper_trading/bars_cl5m.csv", "WTI Crude Oil (CL=F)"),
]


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

    for symbol, daily_path, five_min_path, label in INDEX_FUTURES:
        try:
            daily_df = _fetch_history(symbol, period="10y", interval="1d")
            n = merge_bars_csv(daily_path, _df_to_candles(daily_df), date_only=True)
            print(f"{daily_path}: {n} rows ({len(daily_df)} fetched this run)")
            wrote_any = True
        except Exception as exc:
            print(f"WARN daily {label} fetch failed this run - {exc}")

        try:
            intraday_df = _fetch_history(symbol, period="60d", interval="5m")
            n = merge_bars_csv(five_min_path, _df_to_candles(intraday_df), date_only=False)
            print(f"{five_min_path}: {n} rows ({len(intraday_df)} fetched this run)")
            wrote_any = True
        except Exception as exc:
            print(f"WARN 5-minute {label} fetch failed this run - {exc}")

    if not wrote_any:
        raise SystemExit("All index futures fetches failed this run - no data written")


if __name__ == "__main__":
    main()
