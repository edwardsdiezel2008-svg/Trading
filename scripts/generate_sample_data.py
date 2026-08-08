"""Generate small synthetic tick-log CSVs so the backtest pipeline can be
exercised end-to-end before real NASDAQ/futures logs are downloaded.

This is NOT real market data - it's a random walk that deliberately alternates
between trending and mean-reverting regimes (with occasional vol spikes) so
that trend-following and mean-reversion strategies each get stretches of data
where they should plausibly win or lose, which is what makes the regime
attribution report meaningful to look at.

Usage: python scripts/generate_sample_data.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OUT_DIR = "data/sample"


def generate_ticks(
    start_price: float,
    n_ticks: int,
    start_time: str,
    seconds_between_ticks: float,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    prices = np.empty(n_ticks)
    price = start_price

    regime_len = 400
    i = 0
    while i < n_ticks:
        this_len = min(regime_len, n_ticks - i)
        regime = rng.choice(["trend_up", "trend_down", "mean_revert", "high_vol_chop"], p=[0.2, 0.2, 0.4, 0.2])
        base_level = price

        for j in range(this_len):
            if regime == "trend_up":
                drift, vol = 0.008, 0.05
                price += drift + rng.normal(0, vol)
            elif regime == "trend_down":
                drift, vol = -0.008, 0.05
                price += drift + rng.normal(0, vol)
            elif regime == "mean_revert":
                pull, vol = 0.03, 0.04
                price += pull * (base_level - price) + rng.normal(0, vol)
            else:  # high_vol_chop
                vol = 0.15
                price += rng.normal(0, vol)
            price = max(price, 0.01)
            prices[i + j] = price
        i += this_len

    timestamps = pd.date_range(start=start_time, periods=n_ticks, freq=pd.Timedelta(seconds=seconds_between_ticks))
    sizes = rng.integers(1, 50, size=n_ticks)
    return pd.DataFrame({"timestamp": timestamps, "price": np.round(prices, 2), "size": sizes})


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    # ~35 days of sparse (15s) synthetic ticks - enough span for CAGR/Calmar to
    # be meaningful, small enough to generate and backtest quickly. Real
    # downloaded tick logs will be far denser; the loader doesn't care either way.
    aapl = generate_ticks(start_price=190.0, n_ticks=200_000, start_time="2026-01-05 09:30:00", seconds_between_ticks=15, seed=42)
    aapl.to_csv(f"{OUT_DIR}/NASDAQ_AAPL_ticks.csv", index=False)
    print(f"Wrote {len(aapl):,} ticks to {OUT_DIR}/NASDAQ_AAPL_ticks.csv")

    es = generate_ticks(start_price=5800.0, n_ticks=200_000, start_time="2026-01-05 09:30:00", seconds_between_ticks=15, seed=7)
    es.to_csv(f"{OUT_DIR}/ES_ticks.csv", index=False)
    print(f"Wrote {len(es):,} ticks to {OUT_DIR}/ES_ticks.csv")


if __name__ == "__main__":
    main()
