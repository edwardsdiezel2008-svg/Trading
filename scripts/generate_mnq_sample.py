"""Generate a synthetic Micro E-mini Nasdaq-100 (MNQ) 1-minute bar dataset so
the AuctionMarketProfileStrategy (and the rest of the strategy library) can be
backtested end-to-end before real MNQ data is downloaded.

This is NOT real market data. Bars are generated directly (not resampled from
ticks) for RTH-only sessions (9:30-16:00 ET, weekdays) so each calendar day is
a clean, self-contained session - matching the classic Market Profile
assumption of one profile per session. Real MNQ trades nearly 24 hours; this
is a deliberate simplification for a synthetic dataset, not a claim about the
real product's hours.

Each session alternates between a trend leg and a balance (rotational) leg,
with volume shaped like a real day (busier at the open and close), so
session/week/month volume profiles actually have distinct POC/value-area
shapes to trade against - a flat random walk would make the whole strategy
untestable.

Usage: python scripts/generate_mnq_sample.py [--days 90] [--seed 11]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

OUT_DIR = "data/sample"
BARS_PER_SESSION = 390  # 9:30-16:00 ET, 1-minute bars


def _session_volume_shape(n: int, rng: np.random.Generator) -> np.ndarray:
    """U-shaped intraday volume: heavier at the open and close, lighter midday."""
    t = np.linspace(0, 1, n)
    shape = 1.0 + 1.8 * (t - 0.5) ** 2 * 4  # parabola, ~1x midday to ~2.8x at edges
    noise = rng.lognormal(mean=0, sigma=0.35, size=n)
    return np.maximum(shape * noise, 0.05)


def _generate_session(open_price: float, rng: np.random.Generator) -> pd.DataFrame:
    n = BARS_PER_SESSION
    regime = rng.choice(["trend_up", "trend_down", "balance"], p=[0.3, 0.3, 0.4])

    price = open_price
    opens = np.empty(n)
    highs = np.empty(n)
    lows = np.empty(n)
    closes = np.empty(n)

    if regime == "balance":
        pull, vol = 0.05, 0.9
    else:
        drift = 0.35 if regime == "trend_up" else -0.35
        vol = 1.1

    for i in range(n):
        opens[i] = price
        if regime == "balance":
            price += pull * (open_price - price) + rng.normal(0, vol)
        else:
            price += drift + rng.normal(0, vol)
        price = max(price, 1.0)
        bar_range = abs(rng.normal(0, vol)) + 0.25
        highs[i] = max(opens[i], price) + bar_range * rng.uniform(0, 0.6)
        lows[i] = min(opens[i], price) - bar_range * rng.uniform(0, 0.6)
        closes[i] = price

    base_volume = rng.integers(150, 400)
    volumes = np.round(_session_volume_shape(n, rng) * base_volume).astype(int)
    volumes = np.maximum(volumes, 1)

    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes})


def generate_mnq_bars(days: int, seed: int, start_price: float = 20000.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sessions = []
    price = start_price
    session_dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)

    for date in session_dates:
        session = _generate_session(price, rng)
        idx = pd.date_range(start=date + pd.Timedelta(hours=9, minutes=30), periods=BARS_PER_SESSION, freq="1min")
        session.index = idx
        sessions.append(session)
        price = session["close"].iloc[-1]

    bars = pd.concat(sessions)
    bars.index.name = "timestamp"
    return bars


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=90, help="Number of weekday sessions to generate")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--start-price", type=float, default=20000.0)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    bars = generate_mnq_bars(args.days, args.seed, args.start_price)
    out_path = f"{OUT_DIR}/MNQ_1Min_bars.csv"
    bars.reset_index().to_csv(out_path, index=False)
    print(f"Wrote {len(bars):,} 1-min bars ({args.days} sessions) to {out_path}")


if __name__ == "__main__":
    main()
