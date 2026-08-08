import numpy as np
import pandas as pd
import pytest

from src.backtest.strategies.base import Strategy
from src.backtest.strategies.regime_filter import RegimeFilteredStrategy


class AlwaysLong(Strategy):
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=bars.index)


def _trending_then_flat_bars(n_trend=150, n_flat=150, seed=1):
    up = np.linspace(100, 300, n_trend)
    rng = np.random.default_rng(seed)
    flat = 300 + rng.normal(0, 0.05, n_flat)
    price = np.concatenate([up, flat])
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    return pd.DataFrame({"open": price, "high": price + 0.2, "low": price - 0.2, "close": price, "volume": 100}, index=idx)


def test_requires_exactly_one_of_excluded_or_allowed():
    with pytest.raises(ValueError):
        RegimeFilteredStrategy(AlwaysLong())
    with pytest.raises(ValueError):
        RegimeFilteredStrategy(AlwaysLong(), excluded_regimes={"ranging/low_vol"}, allowed_regimes={"trending/low_vol"})


def test_excluded_regime_bars_are_flattened():
    bars = _trending_then_flat_bars()
    from src.backtest.regime import classify_regimes
    regimes = classify_regimes(bars)

    strat = RegimeFilteredStrategy(AlwaysLong(), excluded_regimes={"ranging/low_vol"})
    signals = strat.generate_signals(bars)

    excluded_mask = regimes["regime"] == "ranging/low_vol"
    assert (signals[excluded_mask] == 0).all()
    # bars not in the excluded regime keep the base strategy's signal (1)
    kept_mask = regimes["regime"].notna() & ~excluded_mask
    assert (signals[kept_mask] == 1).all()


def test_allowed_regime_only_trades_there():
    bars = _trending_then_flat_bars()
    from src.backtest.regime import classify_regimes
    regimes = classify_regimes(bars)

    strat = RegimeFilteredStrategy(AlwaysLong(), allowed_regimes={"trending/low_vol"})
    signals = strat.generate_signals(bars)

    allowed_mask = regimes["regime"] == "trending/low_vol"
    assert (signals[allowed_mask] == 1).all()
    assert (signals[~allowed_mask] == 0).all()
    # unclassified warmup bars are blocked too, not left as-is
    assert (signals[regimes["regime"].isna()] == 0).all()


def test_name_reflects_filter_direction():
    excluded = RegimeFilteredStrategy(AlwaysLong(), excluded_regimes={"ranging/high_vol"})
    allowed = RegimeFilteredStrategy(AlwaysLong(), allowed_regimes={"trending/low_vol"})
    assert "not " in excluded.name
    assert "only " in allowed.name
    assert "ranging/high_vol" in excluded.name
    assert "trending/low_vol" in allowed.name
