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

import argparse
import csv
import datetime
import json
import math
import os
import time

import requests

BASE_URL = "https://api.crypto.com/exchange/v1/public"
# Funding rates are a derivatives-only concept and live on a separate API
# host from spot/exchange endpoints - confirmed via Crypto.com's own docs,
# not something the MCP tool ever exposed a working path for.
DERIV_BASE_URL = "https://deriv-api.crypto.com/v1/public"
# Independent of Crypto.com entirely - alternative.me's Fear & Greed Index
# is a free, public, non-manipulable daily sentiment read across the whole
# crypto market (not BTC-specific), used here as a regime signal alongside
# pure price data.
FEAR_GREED_URL = "https://api.alternative.me/fng/"
CANDLE_COUNT = 300
ORDER_BOOK_DEPTH = 10
BACKFILL_MAX_CANDLES = 6000

BTC_SYMBOL = "BTC_USDT"
BTC_PERP_SYMBOL = "BTCUSD-PERP"
ETH_SYMBOL = "ETH_USDT"
ETH_PERP_SYMBOL = "ETHUSD-PERP"
SOL_SYMBOL = "SOL_USDT"
SOL_PERP_SYMBOL = "SOLUSD-PERP"

# (symbol, bars file) - the other liquid instruments tracked alongside BTC,
# added so paper-trading results can be checked for whether a strategy's
# edge is BTC-specific or holds up more generally. Daily only for now.
OTHER_INSTRUMENTS = [
    (ETH_SYMBOL, "paper_trading/bars_eth.csv"),
    (SOL_SYMBOL, "paper_trading/bars_sol.csv"),
]

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
    # A first attempt to reach ~100 by guessing well-known meme ticker
    # names failed hard: 50 of 51 guesses didn't exist on this exchange
    # (only BONEUSD hit). Crypto.com Exchange is a curated, mainstream
    # listing - most memecoins trade on DEXs or degen-focused exchanges
    # instead. Re-curated from the exchange's *actual* public instrument
    # list (scripts/list_all_tickers.py) instead of guessing further -
    # these are confirmed real listings, not guesses. The realistic
    # ceiling for this data source is roughly 55-60 coins, not 100.
    "BONEUSD", "BASEDUSD", "CLANKERUSD", "ELIZAOSUSD", "LOAFUSD", "PUMPUSD",
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


def _get(path, params=None, retries=3, base_url=BASE_URL):
    url = f"{base_url}/{path}"
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


def fetch_candlestick_paginated(instrument_name, timeframe, max_candles=BACKFILL_MAX_CANDLES, page_size=CANDLE_COUNT):
    """Walk further back in time than a single call's page_size cap allows,
    by requesting progressively older pages via end_ts. Stops once a page
    adds no new candles (either the API doesn't actually support end_ts
    pagination and keeps returning the same latest page, or history is
    exhausted) or once max_candles is reached.

    The end_ts param name/semantics are inferred from common exchange API
    conventions, not confirmed docs - this sandbox can't reach
    exchange-docs.crypto.com to check. If it's wrong, every page will come
    back identical and the "no new candles" guard below will stop after
    one extra page instead of looping forever - watch the printed page
    logs when this runs to tell the difference from a real, older page.
    """
    all_candles = {}
    end_ts = None
    page_num = 0
    while len(all_candles) < max_candles:
        page_num += 1
        params = {
            "instrument_name": _normalize_instrument(instrument_name),
            "timeframe": timeframe,
            "count": page_size,
        }
        if end_ts is not None:
            params["end_ts"] = end_ts
        result = _get("get-candlestick", params)
        page = result["data"]
        print(f"  {instrument_name} page {page_num}: {len(page)} candles, end_ts={end_ts}")
        if not page:
            break
        before = len(all_candles)
        for c in page:
            all_candles[_candle_timestamp(c)] = c
        oldest_ts = min(_candle_timestamp(c) for c in page)
        new_end_ts = int(oldest_ts.timestamp() * 1000) - 1
        if len(all_candles) == before or (end_ts is not None and new_end_ts >= end_ts):
            print(f"  {instrument_name}: no new candles on page {page_num} - stopping")
            break
        end_ts = new_end_ts
        if len(page) < page_size:
            break
        time.sleep(0.2)
    return sorted(all_candles.values(), key=_candle_timestamp)


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


def _normalize_book_level(level):
    """A book level has shown up as [price, size, num_orders] and as
    {"price":.., "quantity":..} across exchange API generations - handle
    both and return a plain [price_str, size_str] pair."""
    if isinstance(level, (list, tuple)):
        return [str(level[0]), str(level[1] if len(level) > 1 else "0")]
    if isinstance(level, dict):
        price = _first(level, "price", "p")
        size = _first(level, "quantity", "size", "q", "s", default="0")
        return [str(price), str(size)]
    return [str(level), "0"]


def fetch_order_book(instrument_name, depth=ORDER_BOOK_DEPTH):
    result = _get("get-book", {
        "instrument_name": _normalize_instrument(instrument_name),
        "depth": depth,
    })
    # Seen shapes: {"depth": N, "data": [{"bids": [...], "asks": [...], "t": ...}]}
    # and directly {"bids": [...], "asks": [...]} at the top level.
    entry = result
    if isinstance(result.get("data"), list) and result["data"]:
        entry = result["data"][0]
    bids = [_normalize_book_level(lv) for lv in entry.get("bids", [])]
    asks = [_normalize_book_level(lv) for lv in entry.get("asks", [])]
    ts = _first(entry, "t", "timestamp")
    if isinstance(ts, (int, float)):
        ts = datetime.datetime.utcfromtimestamp(ts / 1000).isoformat() + "Z"
    return {"bids": bids, "asks": asks, "timestamp": ts or ""}


def fetch_funding_rate(instrument_name=BTC_PERP_SYMBOL, count=1):
    result = _get("get-valuations", {
        "instrument_name": instrument_name,
        "valuation_type": "funding_rate",
        "count": count,
    }, base_url=DERIV_BASE_URL)
    data = result.get("data") if isinstance(result, dict) else result
    if not data:
        return None
    latest = data[0]
    print(f"DEBUG: sample funding rate entry keys: {sorted(latest.keys())}")
    value = _first(latest, "value", "v", "funding_rate", default="0")
    ts = _first(latest, "t", "timestamp")
    if isinstance(ts, (int, float)):
        ts = datetime.datetime.utcfromtimestamp(ts / 1000).isoformat() + "Z"
    return {"rate": str(value), "timestamp": ts or "", "instrument_name": instrument_name}


def fetch_fear_greed():
    """alternative.me's response shape: {"data": [{"value": "34",
    "value_classification": "Fear", "timestamp": "<unix seconds>", ...}], ...}
    - a different host/vendor entirely from Crypto.com, so field names and
    conventions aren't expected to match; kept defensive anyway since this
    also runs unattended."""
    resp = requests.get(FEAR_GREED_URL, params={"limit": 1}, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data") if isinstance(body, dict) else body
    if not data:
        return None
    latest = data[0]
    print(f"DEBUG: sample fear/greed entry keys: {sorted(latest.keys())}")
    value = _first(latest, "value", default=None)
    classification = _first(latest, "value_classification", default="")
    ts = _first(latest, "timestamp")
    if ts is not None:
        try:
            ts = datetime.datetime.utcfromtimestamp(int(ts)).isoformat() + "Z"
        except (TypeError, ValueError):
            pass
    return {"value": int(value) if value is not None else None, "classification": classification, "timestamp": ts or ""}


def _candle_timestamp(c):
    """Crypto.com's REST responses have used both a short epoch-ms shape
    (t/o/h/l/c/v) and a long ISO-timestamp shape (timestamp/open/high/low/
    close/volume) across API versions - handle both defensively since this
    runs unattended with nobody around to notice a silent format change."""
    ts_raw = c.get("t", c.get("timestamp"))
    if isinstance(ts_raw, (int, float)):
        return datetime.datetime.utcfromtimestamp(ts_raw / 1000)
    return datetime.datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)


def _sanitize_ohlc(o, h, l, cl):
    """Crypto.com's deep historical candles (2020-2021 era, seen via
    --backfill) occasionally have low=0 with an otherwise sane open/high/
    close - a single bad tick, not a real price. A zero/negative or
    otherwise impossible low blows up any ATR/range-based strategy that
    reads it (a fake near-100% true-range spike). Clamp low into a sane
    range instead of trusting it blindly; leave everything else alone."""
    try:
        o, h, l, cl = float(o), float(h), float(l), float(cl)
    except (TypeError, ValueError):
        return o, h, l, cl
    lower_bound = min(o, cl)
    if l <= 0 or l > lower_bound:
        l = lower_bound
    return o, h, l, cl


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

    skipped = 0
    for c in candles:
        dt = _candle_timestamp(c)
        ts = dt.strftime("%Y-%m-%d") if date_only else dt.strftime("%Y-%m-%d %H:%M:%S")
        o = c.get("o", c.get("open"))
        h = c.get("h", c.get("high"))
        l = c.get("l", c.get("low"))
        cl = c.get("c", c.get("close"))
        v = c.get("v", c.get("volume", 0))
        o, h, l, cl = _sanitize_ohlc(o, h, l, cl)
        # _sanitize_ohlc only clamps a bad low - an unparseable or NaN
        # o/h/l/close (a real Yahoo Finance failure mode: a blank field for
        # one date) passes through untouched, which would otherwise write
        # garbage straight into the permanent historical CSV. That corrupted
        # this project once already: load_bars loaded the bad row silently,
        # poisoning run_backtest's cumulative equity sum for every bar after
        # it and crashing the site build downstream. Skip the whole candle
        # rather than commit it - a missing bar is much cheaper to recover
        # from than a bad one baked into history.
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (o, h, l, cl)):
            skipped += 1
            continue
        rows[ts] = [ts, o, h, l, cl, v]
    if skipped:
        print(f"WARN merge_bars_csv({path}): skipped {skipped} candle(s) with unparseable/non-finite OHLC")

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for ts in sorted(rows.keys()):
            w.writerow(rows[ts])
    return len(rows)


def backfill_daily_history(max_candles=BACKFILL_MAX_CANDLES):
    """One-time deep backfill for BTC + the other tracked instruments'
    daily bars, via pagination. NOT called by the normal hourly run (see
    main()) - daily candles barely change hour to hour, so relying on
    hourly incremental fetches alone would take years to accumulate real
    depth. Run manually via the backfill-history workflow instead."""
    targets = [(BTC_SYMBOL, "paper_trading/bars.csv")] + OTHER_INSTRUMENTS
    for symbol, path in targets:
        print(f"Backfilling {symbol} -> {path} (up to {max_candles} candles)...")
        try:
            candles = fetch_candlestick_paginated(symbol, "1D", max_candles=max_candles)
            n = merge_bars_csv(path, candles, date_only=True)
            print(f"{path}: {n} rows after backfill ({len(candles)} candles fetched this run)")
        except Exception as e:
            print(f"WARN: backfill failed for {symbol}: {e}")


def main():
    candles = fetch_candlestick(BTC_SYMBOL, "1D")
    n = merge_bars_csv("paper_trading/bars.csv", candles, date_only=True)
    print(f"bars.csv: {n} rows")

    candles = fetch_candlestick(BTC_SYMBOL, "15m")
    n = merge_bars_csv("paper_trading/bars_15m.csv", candles)
    print(f"bars_15m.csv: {n} rows")

    for symbol, path in OTHER_INSTRUMENTS:
        try:
            candles = fetch_candlestick(symbol, "1D")
            n = merge_bars_csv(path, candles, date_only=True)
            print(f"{path}: {n} rows")
        except Exception as e:
            print(f"WARN: skipping {symbol} daily fetch: {e}")

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

    book = None
    try:
        book = fetch_order_book(BTC_SYMBOL)
        print(f"order book: {len(book['bids'])} bid levels, {len(book['asks'])} ask levels")
    except Exception as e:
        print(f"WARN: order book fetch failed: {e}")

    funding = None
    try:
        funding = fetch_funding_rate(BTC_PERP_SYMBOL)
        print(f"funding rate: {funding}")
    except Exception as e:
        print(f"WARN: funding rate fetch failed: {e}")

    if book is not None or funding is not None:
        with open("paper_trading/btc_market_snapshot.json", "w") as f:
            json.dump({
                "updated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
                "order_book": book,
                "funding_rate": funding,
            }, f, indent=2)
        print("btc_market_snapshot.json written")

    # ETH/SOL perpetual funding rates - only field the leveraged ETH/SOL
    # perp tracks need (no order book fetch for these, unlike BTC, since
    # nothing currently reads one for them). Each asset's rate is genuinely
    # different (it reflects that asset's own long/short positioning
    # imbalance) so this can't be approximated by reusing BTC's.
    for label, perp_symbol, out_path in [
        ("ETH", ETH_PERP_SYMBOL, "paper_trading/eth_market_snapshot.json"),
        ("SOL", SOL_PERP_SYMBOL, "paper_trading/sol_market_snapshot.json"),
    ]:
        try:
            asset_funding = fetch_funding_rate(perp_symbol)
            print(f"{label} funding rate: {asset_funding}")
        except Exception as e:
            print(f"WARN: {label} funding rate fetch failed: {e}")
            continue
        if asset_funding is not None:
            with open(out_path, "w") as f:
                json.dump({
                    "updated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
                    "funding_rate": asset_funding,
                }, f, indent=2)
            print(f"{out_path} written")

    try:
        fng = fetch_fear_greed()
        print(f"fear/greed: {fng}")
        if fng is not None:
            with open("paper_trading/fear_greed.json", "w") as f:
                json.dump({
                    "updated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
                    **fng,
                }, f, indent=2)
            print("fear_greed.json written")
    except Exception as e:
        print(f"WARN: fear/greed fetch failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill", action="store_true",
                         help="One-time deep history backfill (BTC/ETH/SOL daily) via pagination, "
                              "instead of the normal hourly incremental fetch.")
    parser.add_argument("--max-candles", type=int, default=BACKFILL_MAX_CANDLES,
                         help="Cap on candles to pull per symbol during --backfill.")
    args = parser.parse_args()
    if args.backfill:
        backfill_daily_history(max_candles=args.max_candles)
    else:
        main()
