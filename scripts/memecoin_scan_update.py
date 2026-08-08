"""Scan a curated list of meme coins listed on Crypto.com Exchange for
price-breakout momentum, using the same Donchian-channel and ATR logic as
the backtest engine's own breakout strategies.

This does NOT predict which coin will "blow up" - it flags coins whose price
has already broken above their recent trading range, ranked by how large
that breakout is relative to the coin's own recent volatility (ATR). It is a
momentum-already-in-progress detector, not a forecast, and it only covers
established coins already listed on the exchange (not new/micro-cap
launches).

This script does NOT fetch data itself - it has no network access here. Each
coin's bars file (paper_trading/memecoins/<SYMBOL>.csv) must already be
updated with the latest candle(s) before calling this.

Usage: python scripts/memecoin_scan_update.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.backtest.data_loader import load_bars

BARS_DIR = "paper_trading/memecoins"
OUTPUT_PATH = "paper_trading/memecoin_scan.json"
LOOKBACK = 20
ATR_PERIOD = 14
MIN_BARS = LOOKBACK + ATR_PERIOD + 1

MEME_COINS = [
    "DOGEUSD", "SHIBUSD", "PEPEUSD", "FLOKIUSD", "BONKUSD", "WIFUSD",
    "FARTCOINUSD", "TRUMPUSD", "BOMEUSD", "HMSTRUSD", "ORDIUSD",
]


def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def scan_coin(symbol: str) -> dict | None:
    path = f"{BARS_DIR}/{symbol}.csv"
    if not os.path.exists(path):
        return None
    bars = load_bars(path, freq="1h")
    if len(bars) < MIN_BARS:
        return {
            "symbol": symbol, "status": "insufficient_data",
            "bar_count": len(bars), "min_bars_needed": MIN_BARS,
        }

    prior_high = bars["high"].rolling(LOOKBACK).max().shift(1)
    atr = _atr(bars, ATR_PERIOD)
    close = bars["close"]

    latest_close = float(close.iloc[-1])
    latest_prior_high = float(prior_high.iloc[-1])
    latest_atr = float(atr.iloc[-1])
    is_breakout = latest_close > latest_prior_high
    breakout_pct = (latest_close / latest_prior_high - 1) * 100 if latest_prior_high else 0.0
    breakout_strength_atr = (
        (latest_close - latest_prior_high) / latest_atr if latest_atr > 0 else 0.0
    )

    return {
        "symbol": symbol,
        "status": "ok",
        "price": latest_close,
        "prior_20bar_high": latest_prior_high,
        "atr_14": latest_atr,
        "is_breakout": bool(is_breakout),
        "breakout_pct": round(breakout_pct, 3),
        "breakout_strength_atr": round(breakout_strength_atr, 3),
        "bar_count": len(bars),
        "as_of": str(bars.index[-1]),
    }


def main():
    results = []
    for symbol in MEME_COINS:
        r = scan_coin(symbol)
        if r is not None:
            results.append(r)

    ok = [r for r in results if r["status"] == "ok"]
    ranked = sorted(ok, key=lambda r: r["breakout_strength_atr"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    skipped = [r for r in results if r["status"] != "ok"]

    out = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lookback_bars": LOOKBACK,
        "atr_period": ATR_PERIOD,
        "ranked": ranked,
        "skipped": skipped,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Updated {OUTPUT_PATH} ({len(ranked)} scanned, {len(skipped)} skipped)")
    for r in ranked[:5]:
        flag = "BREAKOUT" if r["is_breakout"] else "-"
        print(f"  #{r['rank']} {r['symbol']}: {flag} strength={r['breakout_strength_atr']:+.2f} ATR, {r['breakout_pct']:+.2f}% vs 20h high")


if __name__ == "__main__":
    main()
