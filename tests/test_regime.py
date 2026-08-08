import numpy as np
import pandas as pd

from src.backtest.regime import classify_regimes


def test_strong_trend_is_classified_as_trending():
    n = 150
    price = np.linspace(100, 300, n)  # clean, strong uptrend
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    bars = pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 100}, index=idx)

    regimes = classify_regimes(bars, adx_period=14)
    tail = regimes["trend_regime"].iloc[-30:]
    assert (tail == "trending").mean() > 0.8


def test_flat_noisy_price_is_classified_as_ranging():
    rng = np.random.default_rng(0)
    n = 150
    price = 100 + rng.normal(0, 0.3, n).cumsum() * 0  # exactly flat
    price = 100 + rng.normal(0, 0.05, n)  # tiny noise around a constant level
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    bars = pd.DataFrame({"open": price, "high": price + 0.05, "low": price - 0.05, "close": price, "volume": 100}, index=idx)

    regimes = classify_regimes(bars, adx_period=14)
    tail = regimes["trend_regime"].iloc[-30:]
    assert (tail == "ranging").mean() > 0.8


def test_regime_label_is_combination_of_trend_and_vol():
    n = 150
    price = np.linspace(100, 300, n)
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    bars = pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 100}, index=idx)

    regimes = classify_regimes(bars)
    valid = regimes.dropna(subset=["regime"])
    for label, row in zip(valid["regime"], valid.itertuples()):
        assert label == f"{row.trend_regime}/{row.vol_regime}"
