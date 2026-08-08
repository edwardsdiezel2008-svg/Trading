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
    assert len(strategies) == 7
    assert len({s.name for s in strategies}) == 7


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
