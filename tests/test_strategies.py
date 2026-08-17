import numpy as np
import pandas as pd
import pytest

from src.backtest.strategies import (
    ATRVolatilityBreakout,
    AuctionMarketProfileStrategy,
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
    AuctionMarketProfileStrategy(),
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
    assert len(strategies) == 8
    assert len({s.name for s in strategies}) == 8


def _synthetic_multiday_bars(n_sessions=30, bars_per_session=100, seed=3):
    rng = np.random.default_rng(seed)
    sessions = []
    price = 20000.0
    for date in pd.bdate_range("2026-01-05", periods=n_sessions):
        opens = np.empty(bars_per_session)
        closes = np.empty(bars_per_session)
        for i in range(bars_per_session):
            opens[i] = price
            price += rng.normal(0, 2.0)
            price = max(price, 1.0)
            closes[i] = price
        highs = np.maximum(opens, closes) + rng.uniform(0, 2.0, bars_per_session)
        lows = np.minimum(opens, closes) - rng.uniform(0, 2.0, bars_per_session)
        volume = rng.integers(50, 300, bars_per_session)
        idx = pd.date_range(date + pd.Timedelta(hours=9, minutes=30), periods=bars_per_session, freq="1min")
        sessions.append(pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": volume}, index=idx))
    return pd.concat(sessions)


def test_auction_market_profile_uses_prior_sessions_only():
    # With only one session of history, there's no completed prior session to
    # reference yet, so the strategy must stay flat - it should never open a
    # position off same-session (lookahead) levels.
    bars = _synthetic_multiday_bars(n_sessions=1, bars_per_session=200)
    strategy = AuctionMarketProfileStrategy()
    signals = strategy.generate_signals(bars)
    assert (signals == 0).all()


def test_auction_market_profile_trades_once_prior_sessions_exist():
    bars = _synthetic_multiday_bars(n_sessions=30, bars_per_session=100)
    strategy = AuctionMarketProfileStrategy()
    signals = strategy.generate_signals(bars)
    assert len(signals) == len(bars)
    assert set(signals.unique()).issubset({-1, 0, 1})
    # Sessions 2+ have at least a prior-session profile to reference.
    assert (signals.iloc[100:] != 0).any()


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
