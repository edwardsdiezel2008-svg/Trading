"""Fetch daily QQQ (Invesco QQQ Trust) bars from Stooq's free, unauthenticated
CSV endpoint - the Nasdaq-100 tracking proxy used by the paper-trading
dashboard's "Nasdaq-100 Futures" track.

Why QQQ and not real NQ/MNQ futures data: genuine CME Nasdaq-100 futures
history (tick or bar level) isn't available from any public, free, API-key-
free source - every option found (EODHD, Financial Modeling Prep, Databento,
kibot, firstratedata) requires at least a free account/API key, and none of
those are things this unattended hourly pipeline can hold credentials for
without a GitHub secret the user would have to set up. QQQ is the most
liquid, easily-verified public proxy: it tracks the Nasdaq-100 index almost
exactly, trades on a real exchange, and Stooq serves its full daily history
as a plain CSV with no key, account, or CAPTCHA required.

Why daily-only: Stooq's per-symbol download endpoint used here only returns
daily/weekly/monthly bars unauthenticated - true intraday data exists on
Stooq but only via a CAPTCHA-gated bulk archive download, which can't be
automated in an unattended pipeline. Real NQ/MNQ futures also trade nearly
24 hours a day, while QQQ only trades during (extended) NYSE/Nasdaq session
hours - another reason daily closing bars are a defensible proxy but
intraday wouldn't be.

Usage: python scripts/fetch_nasdaq_data.py
"""
from __future__ import annotations

import csv
import io
import sys
import time

sys.path.insert(0, ".")

import requests

from scripts.fetch_market_data import merge_bars_csv

STOOQ_CSV_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
QQQ_SYMBOL = "qqq.us"
BARS_PATH = "paper_trading/bars_nq.csv"


def fetch_stooq_daily_csv(symbol=QQQ_SYMBOL, retries=3):
    url = STOOQ_CSV_URL.format(symbol=symbol)
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=20)
            if not resp.ok:
                raise RuntimeError(f"{resp.status_code} for {url}: {resp.text[:300]}")
            text = resp.text
            # Stooq returns a plain "No data" (or similar short) body instead
            # of an HTTP error for an unrecognized symbol - fail loudly
            # rather than silently caching a near-empty bars file.
            if len(text.splitlines()) < 2:
                raise RuntimeError(f"Stooq returned no data for {symbol}: {text[:200]!r}")
            return text
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch Stooq CSV for {symbol} after {retries} attempts: {last_err}")


def parse_stooq_csv(text):
    """Stooq's per-symbol download is a plain CSV: Date,Open,High,Low,Close,Volume
    (case as shown). Returns a list of candle dicts in the {timestamp, open,
    high, low, close, volume} shape merge_bars_csv() already expects."""
    reader = csv.DictReader(io.StringIO(text))
    candles = []
    for row in reader:
        lower = {k.lower(): v for k, v in row.items()}
        date = lower.get("date")
        if not date:
            continue
        try:
            candles.append({
                "timestamp": date,
                "open": float(lower["open"]),
                "high": float(lower["high"]),
                "low": float(lower["low"]),
                "close": float(lower["close"]),
                "volume": float(lower.get("volume") or 0),
            })
        except (KeyError, ValueError):
            continue
    return candles


def main():
    text = fetch_stooq_daily_csv()
    candles = parse_stooq_csv(text)
    if not candles:
        raise SystemExit(f"Parsed 0 usable rows from Stooq's response for {QQQ_SYMBOL} - format may have changed.")
    n = merge_bars_csv(BARS_PATH, candles, date_only=True)
    print(f"{BARS_PATH}: {n} rows ({len(candles)} candles fetched this run)")


if __name__ == "__main__":
    main()
