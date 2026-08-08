"""Wide meme-coin momentum scan using 24h ticker snapshots (last/high/low/
change/volume), covering a much larger coin universe than
memecoin_scan_update.py's precise hourly-candle scanner.

This trades precision for breadth: it has no rolling multi-hour history, so
it can't compute a real Donchian/ATR breakout - instead it ranks coins by
how close price is sitting to its own 24h high while up on the day, which
is a coarser "already moving, already near the top of its range" heuristic.
Like the precise scanner, this flags momentum already in progress - it does
not predict anything, and coins with thin 24h USD volume are flagged as
low-confidence rather than excluded outright.

This script does NOT fetch data itself - it has no network access here.
paper_trading/memecoins_wide_tickers.json must already be updated with a
fresh 24h ticker snapshot (see paper_trading/README.md).

Usage: python scripts/memecoin_wide_scan.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

TICKERS_PATH = "paper_trading/memecoins_wide_tickers.json"
OUTPUT_PATH = "paper_trading/memecoin_wide_scan.json"
MIN_VOLUME_USD = 10_000  # below this, liquidity is thin enough that the range/price can be easily distorted


def main():
    with open(TICKERS_PATH) as f:
        raw = json.load(f)["symbols"]

    rows = []
    for symbol, t in raw.items():
        last = float(t["last"])
        high = float(t["high"])
        low = float(t["low"])
        change_pct = float(t["change"]) * 100
        volume_usd = float(t["volume_value"])

        range_position = (last - low) / (high - low) if high > low else 0.5
        pct_from_high = (last / high - 1) * 100 if high else 0.0

        rows.append({
            "symbol": symbol,
            "price": last,
            "change_24h_pct": round(change_pct, 3),
            "high_24h": high,
            "low_24h": low,
            "pct_from_24h_high": round(pct_from_high, 3),
            "range_position": round(range_position, 3),
            "volume_24h_usd": round(volume_usd, 2),
            "thin_liquidity": volume_usd < MIN_VOLUME_USD,
            "as_of": t["timestamp"],
        })

    # Rank by range_position (how close to today's high) among coins that are
    # also up on the day - the coarse "already breaking out" heuristic.
    momentum = [r for r in rows if r["change_24h_pct"] > 0]
    ranked = sorted(momentum, key=lambda r: r["range_position"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    not_moving = sorted(
        [r for r in rows if r["change_24h_pct"] <= 0],
        key=lambda r: r["change_24h_pct"], reverse=True,
    )

    out = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(rows),
        "min_volume_usd": MIN_VOLUME_USD,
        "ranked": ranked,
        "not_moving": not_moving,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Updated {OUTPUT_PATH} ({len(rows)} coins, {len(ranked)} up on the day)")
    for r in ranked[:8]:
        thin = " (thin liquidity)" if r["thin_liquidity"] else ""
        print(f"  #{r['rank']} {r['symbol']}: {r['change_24h_pct']:+.2f}% 24h, {r['pct_from_24h_high']:+.2f}% from high{thin}")


if __name__ == "__main__":
    main()
