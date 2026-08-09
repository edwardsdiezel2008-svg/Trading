import numpy as np
import pandas as pd
import pytest

from src.backtest.strategies import (
    ATRVolatilityBreakout,
    BollingerReversion,
    DonchianBreakout,
    MACDMomentum,
    MovingAverageCrossover,
    RSIReversion,
    Supertrend,
    VWAPReversion,
    ZScoreReversion,
    build_default_strategies,
)

ALL = [
    MovingAverageCrossover(),
    DonchianBreakout(),
    MACDMomentum(),
    RSIReversion(),
    BollingerReversion(),
    ZScoreReversion(),
    ATRVolatilityBreakout(),
    Supertrend(),
    VWAPReversion(),
]


def _synthetic_bars(n=300, seed=1):
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0, 1, n))
    price = np.maximum(price, 1)
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    high = price + rng.uniform(0, 1, n)
    low = price - rng.uniform(0, 1, n)
    return pd.DataFrame({"open": price, "high": high, "low": low, "close": price, "volume": 100}, index=idx)


@pytest.mark.parametrize("strategy", ALL, ids=lambda s: s.__class__.__name__)
def test_signals_are_valid_positions(strategy):
    bars = _synthetic_bars()
    signals = strategy.generate_signals(bars)
    assert len(signals) == len(bars)
    assert signals.index.equals(bars.index)
    assert not signals.isna().any()
    assert set(signals.unique()).issubset({-1, 0, 1})


def test_build_default_strategies_returns_one_of_each():
    strategies = build_default_strategies()
    assert len(strategies) == 9
    assert len({s.name for s in strategies}) == 9


def test_ma_crossover_flips_on_clean_trend_reversal():
    # Strictly increasing then strictly decreasing price series - the fast MA
    # should sit above the slow MA on the way up and flip below on the way down.
    up = np.linspace(100, 200, 60)
    down = np.linspace(200, 100, 60)
    price = np.concatenate([up, down])
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 100}, index=idx)

    strategy = MovingAverageCrossover(params={"fast": 5, "slow": 20})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[40] == 1
    assert signals.iloc[-1] == -1


def test_supertrend_flips_on_clean_trend_reversal():
    up = np.linspace(100, 300, 60)
    down = np.linspace(300, 100, 60)
    price = np.concatenate([up, down])
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({
        "open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 100,
    }, index=idx)

    strategy = Supertrend(params={"atr_period": 10, "multiplier": 2.0})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[40] == 1
    assert signals.iloc[-1] == -1


def test_supertrend_band_never_moves_against_the_trend():
    # A ratcheting band is the whole point of Supertrend vs. a plain
    # breakout test - once in an uptrend, a small pullback that doesn't
    # break the lower band must not flip the signal.
    price = np.concatenate([np.linspace(100, 200, 40), [199, 197, 199, 202]])
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({
        "open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 100,
    }, index=idx)
    strategy = Supertrend(params={"atr_period": 10, "multiplier": 3.0})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[35:] == 1).all()


def test_vwap_reversion_goes_long_on_a_sharp_dip_below_vwap():
    # Flat, high-volume price history establishes a stable VWAP, then a
    # sharp one-bar dip should trigger a long entry.
    price = [100.0] * 25 + [90.0] * 5
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({
        "open": price, "high": price, "low": price, "close": price, "volume": 1000,
    }, index=idx)
    strategy = VWAPReversion(params={"window": 20, "entry_pct": 0.02, "exit_pct": 0.005})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 1


def test_vwap_reversion_flat_when_price_tracks_vwap():
    price = [100.0 + (i % 3) * 0.01 for i in range(30)]  # negligible drift
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({
        "open": price, "high": price, "low": price, "close": price, "volume": 1000,
    }, index=idx)
    strategy = VWAPReversion(params={"window": 20, "entry_pct": 0.02, "exit_pct": 0.005})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[20:] == 0).all()
