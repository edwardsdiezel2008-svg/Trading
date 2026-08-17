import numpy as np
import pandas as pd
import pytest

from src.backtest.strategies import (
    ATRVolatilityBreakout,
    BollingerReversion,
    CCIReversion,
    DonchianBreakout,
    EngulfingReversal,
    InsideBarBreakout,
    KeltnerChannelBreakout,
    MACDMomentum,
    MovingAverageCrossover,
    OpeningRangeBreakout,
    ParabolicSAR,
    RSIReversion,
    StochasticReversion,
    Supertrend,
    VWAPReversion,
    ZScoreReversion,
    build_default_strategies,
)

ALL = [
    MovingAverageCrossover(),
    DonchianBreakout(),
    MACDMomentum(),
    ParabolicSAR(),
    RSIReversion(),
    BollingerReversion(),
    ZScoreReversion(),
    StochasticReversion(),
    CCIReversion(),
    ATRVolatilityBreakout(),
    Supertrend(),
    KeltnerChannelBreakout(),
    VWAPReversion(),
    EngulfingReversal(),
    InsideBarBreakout(),
    OpeningRangeBreakout(),
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
    assert len(strategies) == 16
    assert len({s.name for s in strategies}) == 16


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


def _bar(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_engulfing_reversal_goes_long_on_bullish_engulfing():
    # A red candle (10 -> 9) followed by a green candle that fully engulfs
    # its body (8.5 -> 10.5) is a textbook bullish engulfing pattern.
    rows = [_bar(10.0, 10.2, 8.8, 9.0)] * 5 + [_bar(8.5, 10.6, 8.4, 10.5)]
    idx = pd.date_range("2026-01-05", periods=len(rows), freq="1min")
    bars = pd.DataFrame(rows, index=idx)
    strategy = EngulfingReversal(params={"min_body_pct": 0.3})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 1


def test_engulfing_reversal_ignores_weak_body_below_threshold():
    # The engulfing candle's body barely covers half its range (mostly
    # wick) - below a strict min_body_pct this shouldn't count as a signal.
    rows = [_bar(10.0, 10.2, 8.8, 9.0)] * 5 + [_bar(9.4, 12.0, 8.0, 9.6)]
    idx = pd.date_range("2026-01-05", periods=len(rows), freq="1min")
    bars = pd.DataFrame(rows, index=idx)
    strategy = EngulfingReversal(params={"min_body_pct": 0.9})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 0


def test_inside_bar_breakout_goes_long_on_upside_breakout():
    # Mother bar with a wide range, then an inside bar contained within it,
    # then a close above the mother bar's high.
    rows = [
        _bar(100.0, 110.0, 90.0, 105.0),   # mother bar: range 90-110
        _bar(103.0, 106.0, 102.0, 104.0),  # inside bar: range 102-106, well inside
        _bar(105.0, 112.0, 104.0, 111.0),  # breaks above mother high (110)
    ]
    idx = pd.date_range("2026-01-05", periods=len(rows), freq="1min")
    bars = pd.DataFrame(rows, index=idx)
    strategy = InsideBarBreakout(params={"max_range_ratio": 0.6})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 1


def test_inside_bar_breakout_flat_without_a_breakout():
    rows = [
        _bar(100.0, 110.0, 90.0, 105.0),
        _bar(103.0, 106.0, 102.0, 104.0),
        _bar(104.0, 105.0, 103.5, 104.5),  # stays inside the mother range
    ]
    idx = pd.date_range("2026-01-05", periods=len(rows), freq="1min")
    bars = pd.DataFrame(rows, index=idx)
    strategy = InsideBarBreakout(params={"max_range_ratio": 0.6})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 0


def test_opening_range_breakout_goes_long_above_range_and_vwap():
    # First 3 bars (the opening range) trade flat around 100; a later bar
    # closes well above both the opening range high and VWAP.
    rows = [_bar(100.0, 100.5, 99.5, 100.0)] * 3 + [_bar(100.0, 100.2, 99.9, 100.0)] * 2 + [_bar(100.0, 103.0, 100.0, 102.5)]
    idx = pd.date_range("2026-01-05 09:30", periods=len(rows), freq="5min")
    bars = pd.DataFrame(rows, index=idx)
    strategy = OpeningRangeBreakout(params={"range_bars": 3})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 1


def test_opening_range_breakout_resets_flat_at_new_session():
    rows = [_bar(100.0, 100.5, 99.5, 100.0)] * 3 + [_bar(100.0, 100.2, 99.9, 100.0)] * 2 + [_bar(100.0, 103.0, 100.0, 102.5)]
    idx = pd.date_range("2026-01-05 09:30", periods=len(rows), freq="5min")
    bars_day1 = pd.DataFrame(rows, index=idx)
    idx_day2 = pd.date_range("2026-01-06 09:30", periods=3, freq="5min")
    bars_day2 = pd.DataFrame([_bar(100.0, 100.5, 99.5, 100.0)] * 3, index=idx_day2)
    bars = pd.concat([bars_day1, bars_day2])
    strategy = OpeningRangeBreakout(params={"range_bars": 3})
    signals = strategy.generate_signals(bars)
    # Day 2's opening range bars haven't broken out of anything yet - flat.
    assert (signals.iloc[-3:] == 0).all()


def test_opening_range_breakout_session_spans_utc_midnight_correctly():
    # First 3 bars: flat opening range, late in the UTC calendar day but
    # still hours before that date's 9:30 AM ET cash open. Last 3 bars:
    # cross UTC midnight into the next calendar date and break out strongly.
    # A raw UTC-midnight session boundary would wrongly treat the last 3
    # bars as their own brand-new session (never able to break out of an
    # opening range consisting of themselves) - the ET-anchored fix keeps
    # them in the same continuous overnight session as the first 3.
    rows = [_bar(100.0, 100.5, 99.5, 100.0)] * 3
    idx = pd.date_range("2026-08-10 23:45", periods=3, freq="5min")
    rows2 = [_bar(100.0, 103.0, 100.0, 102.5)] * 3
    idx2 = pd.date_range("2026-08-11 00:00", periods=3, freq="5min")
    bars = pd.DataFrame(rows + rows2, index=idx.append(idx2))
    strategy = OpeningRangeBreakout(params={"range_bars": 3})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[3:] == 1).all()


def test_opening_range_breakout_never_fires_on_daily_bars():
    # One bar per session means bar_num is always 0 < range_bars - the
    # strategy should correctly stay flat the whole time.
    price = 100 + np.cumsum(np.random.default_rng(3).normal(0, 1, 50))
    idx = pd.date_range("2026-01-05", periods=50, freq="1D")
    bars = pd.DataFrame({"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 1000}, index=idx)
    strategy = OpeningRangeBreakout(params={"range_bars": 6})
    signals = strategy.generate_signals(bars)
    assert (signals == 0).all()


def test_parabolic_sar_flips_on_clean_trend_reversal():
    up = np.linspace(100, 200, 60)
    down = np.linspace(200, 100, 60)
    price = np.concatenate([up, down])
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({
        "open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 100,
    }, index=idx)

    strategy = ParabolicSAR(params={"af_start": 0.02, "af_max": 0.2})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[40] == 1
    assert signals.iloc[-1] == -1


def test_parabolic_sar_short_history_stays_flat_without_erroring():
    bars = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [100]},
        index=pd.date_range("2026-01-05", periods=1, freq="1min"),
    )
    strategy = ParabolicSAR()
    signals = strategy.generate_signals(bars)
    assert (signals == 0).all()


def test_stochastic_reversion_flat_when_price_never_moves():
    price = [100.0] * 30
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 100}, index=idx)
    strategy = StochasticReversion(params={"period": 14, "d_period": 3, "lower": 20, "upper": 80})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[14:] == 0).all()


def test_stochastic_reversion_goes_long_after_a_sharp_oversold_rebound():
    flat = [100.0] * 20
    decline = list(np.linspace(100, 70, 10))
    rebound = list(np.linspace(70, 110, 15))
    price = flat + decline + rebound
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({
        "open": price, "high": [p + 0.5 for p in price], "low": [p - 0.5 for p in price], "close": price, "volume": 100,
    }, index=idx)
    strategy = StochasticReversion(params={"period": 14, "d_period": 3, "lower": 20, "upper": 80})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[30:] == 1).any()


def test_cci_reversion_goes_long_on_a_sharp_dip_below_the_mean():
    price = [100.0] * 25 + [80.0] * 5
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 100}, index=idx)
    strategy = CCIReversion(params={"period": 20, "entry": 100})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 1


def test_cci_reversion_flat_when_price_never_moves():
    price = [100.0] * 30
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 100}, index=idx)
    strategy = CCIReversion(params={"period": 20, "entry": 100})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[20:] == 0).all()


def test_keltner_breakout_goes_long_on_a_sharp_expansion_beyond_the_band():
    flat = [100.0] * 30
    price = flat + [110.0]
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    high = [p + 0.1 for p in flat] + [110.5]
    low = [p - 0.1 for p in flat] + [100.0]
    bars = pd.DataFrame({"open": price, "high": high, "low": low, "close": price, "volume": 100}, index=idx)
    strategy = KeltnerChannelBreakout(params={"period": 20, "multiplier": 2.0})
    signals = strategy.generate_signals(bars)
    assert signals.iloc[-1] == 1


def test_keltner_breakout_flat_during_quiet_consolidation():
    price = [100.0 + (i % 3) * 0.01 for i in range(40)]
    idx = pd.date_range("2026-01-05", periods=len(price), freq="1min")
    bars = pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 100}, index=idx)
    strategy = KeltnerChannelBreakout(params={"period": 20, "multiplier": 2.0})
    signals = strategy.generate_signals(bars)
    assert (signals.iloc[20:] == 0).all()
