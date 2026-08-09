"""Fetch fresh market data directly from Crypto.com's public REST API (no
authentication required for market data) and merge it into the
paper_trading bar/ticker files this project already uses.

This deliberately does NOT go through the Claude MCP connector - it's a
plain HTTP client, meant to run from infrastructure that doesn't depend on
a Claude session being open (e.g. a GitHub Actions cron job), so paper
trading data keeps updating even when nobody is chatting with Claude.

Requests up to 300 candles per call (the exchange's real cap - much wider
than the 50-candle cap the MCP tool wrapper enforces), which gives a much
bigger safety margin against gaps if a run is ever missed: ~12.5 days of
1h coverage, ~75 hours of 15m coverage, ~300 days of daily coverage.

Usage: python scripts/fetch_market_data.py
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import time

import requests

BASE_URL = "https://api.crypto.com/exchange/v1/public"
CANDLE_COUNT = 300

BTC_SYMBOL = "BTC_USDT"

MEME_PRECISE_SYMBOLS = [
    "DOGEUSD", "SHIBUSD", "PEPEUSD", "FLOKIUSD", "BONKUSD", "WIFUSD",
    "FARTCOINUSD", "TRUMPUSD", "BOMEUSD", "HMSTRUSD", "ORDIUSD",
]

MEME_WIDE_SYMBOLS = [
    "DOGEUSD", "SHIBUSD", "PEPEUSD", "FLOKIUSD", "BONKUSD", "WIFUSD",
    "FARTCOINUSD", "TRUMPUSD", "MELANIAUSD", "BOMEUSD", "MYROUSD",
    "TOSHIUSD", "HMSTRUSD", "DOGSUSD", "NOTUSD", "POPCATUSD", "GOATUSD",
    "PNUTUSD", "MOGUSD", "ORDIUSD", "TURBOUSD", "DEGENUSD", "BANANAUSD",
    "WENUSD", "COQUSD", "USELESSUSD", "CAWUSD", "TROLLUSD", "PONKEUSD",
    "MOODENGUSD", "CATIUSD", "ACTUSD", "AGENTFUNUSD", "CORGIAIUSD",
    "GOATEDUSD", "BINKUSD", "FWOGUSD", "CASHCATUSD", "LUNCUSD",
    "CHILLGUYUSD", "SPXUSD", "ELONUSD", "SNEKUSD", "VINEUSD", "PENGUUSD",
    "LADYSUSD", "GEKKOUSD", "MANEKIUSD", "AIXBTUSD", "BIRBUSD", "HEHEUSD",
]


def _normalize_instrument(symbol):
    """The raw REST API expects underscore-separated pairs (BTC_USDT,
    DOGE_USD); this project's internal naming (and the MCP tool that used
    to front this data) drops the underscore (DOGEUSD). Translate only for
    the outgoing request - all local files keep using the original,
    underscore-free symbol as their key/filename."""
    if "_" in symbol:
        return symbol
    for quote in ("USDT", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)] + "_" + quote
    return symbol


def _get(path, params=None, retries=3):
    url = f"{BASE_URL}/{path}"
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=20)
            if not resp.ok:
                # include the response body - a bare 400/404 with no body
                # text is nearly undebuggable after the fact in CI logs.
                raise RuntimeError(f"{resp.status_code} for {resp.url}: {resp.text[:500]}")
            body = resp.json()
            if body.get("code") not in (0, None):
                raise RuntimeError(f"{path} returned code {body.get('code')}: {body}")
            return body["result"]
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {path} after {retries} attempts: {last_err}")


def fetch_candlestick(instrument_name, timeframe, count=CANDLE_COUNT):
    result = _get("get-candlestick", {
        "instrument_name": _normalize_instrument(instrument_name),
        "timeframe": timeframe,
        "count": count,
    })
    return result["data"]


def fetch_tickers():
    result = _get("get-tickers")
    return result["data"]


_TICKER_SYMBOL_KEYS = ("instrument_name", "i", "symbol", "s")


def _ticker_symbol(t):
    for key in _TICKER_SYMBOL_KEYS:
        if key in t:
            return t[key]
    raise KeyError(
        f"None of {_TICKER_SYMBOL_KEYS} found in ticker entry; actual keys: {sorted(t.keys())}"
    )


def _first(t, *keys, default=None):
    for k in keys:
        if k in t and t[k] is not None:
            return t[k]
    return default


def _normalize_ticker(t):
    """Downstream (memecoin_wide_scan.py) expects last/high/low/change/
    volume_value/timestamp - normalize here so that file doesn't need to
    know or care which exact field names the raw REST API uses (which may
    differ from the MCP tool's normalized shape this project was built
    against; short/abbreviated key names like h/l/a/c/v/vv/t/i are common
    on this exchange's raw API)."""
    ts = _first(t, "timestamp", "t")
    if isinstance(ts, (int, float)):
        ts = datetime.datetime.utcfromtimestamp(ts / 1000).isoformat() + "Z"
    return {
        "last": _first(t, "last", "a", default="0"),
        "high": _first(t, "high", "h", default="0"),
        "low": _first(t, "low", "l", default="0"),
        "change": _first(t, "change", "c", default="0"),
        "volume_value": _first(t, "volume_value", "vv", "v", default="0"),
        "timestamp": ts or "",
    }


def _candle_timestamp(c):
    """Crypto.com's REST responses have used both a short epoch-ms shape
    (t/o/h/l/c/v) and a long ISO-timestamp shape (timestamp/open/high/low/
    close/volume) across API versions - handle both defensively since this
    runs unattended with nobody around to notice a silent format change."""
    ts_raw = c.get("t", c.get("timestamp"))
    if isinstance(ts_raw, (int, float)):
        return datetime.datetime.utcfromtimestamp(ts_raw / 1000)
    return datetime.datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)


def merge_bars_csv(path, candles, date_only=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = {}
    header = ["timestamp", "open", "high", "low", "close", "volume"]
    if os.path.exists(path):
        with open(path) as f:
            r = csv.reader(f)
            header = next(r)
            for row in r:
                rows[row[0]] = row

    for c in candles:
        dt = _candle_timestamp(c)
        ts = dt.strftime("%Y-%m-%d") if date_only else dt.strftime("%Y-%m-%d %H:%M:%S")
        o = c.get("o", c.get("open"))
        h = c.get("h", c.get("high"))
        l = c.get("l", c.get("low"))
        cl = c.get("c", c.get("close"))
        v = c.get("v", c.get("volume", 0))
        rows[ts] = [ts, o, h, l, cl, v]

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for ts in sorted(rows.keys()):
            w.writerow(rows[ts])
    return len(rows)


def main():
    candles = fetch_candlestick(BTC_SYMBOL, "1D")
    n = merge_bars_csv("paper_trading/bars.csv", candles, date_only=True)
    print(f"bars.csv: {n} rows")

    candles = fetch_candlestick(BTC_SYMBOL, "15m")
    n = merge_bars_csv("paper_trading/bars_15m.csv", candles)
    print(f"bars_15m.csv: {n} rows")

    for symbol in MEME_PRECISE_SYMBOLS:
        try:
            candles = fetch_candlestick(symbol, "1h")
        except Exception as e:
            print(f"WARN: skipping {symbol} (precise scanner): {e}")
            continue
        n = merge_bars_csv(f"paper_trading/memecoins/{symbol}.csv", candles)
        print(f"memecoins/{symbol}.csv: {n} rows")

    tickers = fetch_tickers()
    if tickers:
        print(f"DEBUG: sample ticker keys: {sorted(tickers[0].keys())}")
    by_sym = {_ticker_symbol(t): t for t in tickers}
    # tickers come back underscore-separated (DOGE_USD); project keys don't
    # (DOGEUSD) - look up via the same normalization used for candlesticks.
    found = {}
    for s in MEME_WIDE_SYMBOLS:
        norm = _normalize_instrument(s)
        raw = by_sym.get(norm) or by_sym.get(s)
        if raw is not None:
            found[s] = _normalize_ticker(raw)
    missing = [s for s in MEME_WIDE_SYMBOLS if s not in found]
    if missing:
        print(f"WARN: {len(missing)} wide-scan symbols missing from tickers response: {missing}")
    with open("paper_trading/memecoins_wide_tickers.json", "w") as f:
        json.dump({"symbols": found}, f, indent=2)
    print(f"memecoins_wide_tickers.json: {len(found)} symbols")


if __name__ == "__main__":
    main()
