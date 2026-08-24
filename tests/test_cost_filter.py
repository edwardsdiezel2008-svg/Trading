import pandas as pd

from src.backtest.instruments import InstrumentSpec
from src.backtest.strategies.base import Strategy
from src.backtest.strategies.cost_filter import CostAwareFilter


class Alternating(Strategy):
    """Flips direction every single bar - a worst-case whipsaw signal."""
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        n = len(bars)
        return pd.Series([1 if i % 2 == 0 else -1 for i in range(n)], index=bars.index)


def _bars(prices, opens=None):
    idx = pd.date_range("2026-01-05", periods=len(prices), freq="1min")
    opens = opens if opens is not None else prices
    return pd.DataFrame({"open": opens, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)


def _crypto_spec(commission_pct=0.001, slippage_pct=0.0):
    return InstrumentSpec(
        "TEST", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0,
        fractional_units=True, commission_pct=commission_pct, slippage_pct=slippage_pct,
    )


def test_suppresses_every_flip_when_price_never_moves():
    # Flat price -> zero true range -> zero expected move, forever - no
    # position change can ever clear a positive cost floor.
    bars = _bars([100] * 10)
    spec = _crypto_spec(commission_pct=0.001)
    filt = CostAwareFilter(Alternating(), spec, atr_period=2, min_cost_multiple=1.0)
    signal = filt.generate_signals(bars)
    assert (signal == 0).all()


def test_passes_signal_through_once_moves_clear_the_cost_floor():
    # Large swings against a tiny cost floor - the filter should track the
    # inner strategy's signal exactly once ATR has warmed up.
    prices = [100, 120, 90, 140, 80, 150, 70, 160]
    bars = _bars(prices)
    spec = _crypto_spec(commission_pct=0.0001, slippage_pct=0.0)
    inner = Alternating()
    filt = CostAwareFilter(inner, spec, atr_period=2, min_cost_multiple=0.1)

    filtered = filt.generate_signals(bars)
    raw = inner.generate_signals(bars)
    assert filtered.iloc[2:].tolist() == raw.iloc[2:].tolist()


def test_holds_prior_position_instead_of_flattening_when_blocked():
    # A blocked flip must hold the *current* position, not jump to 0 - the
    # strategy stays in whatever it was already doing rather than going
    # flat every time it's denied a trade.
    bars = _bars([100] * 3 + [100.01] * 3)  # tiny move stays below the floor
    spec = _crypto_spec(commission_pct=0.05)  # deliberately huge cost floor
    filt = CostAwareFilter(Alternating(), spec, atr_period=2, min_cost_multiple=5.0)
    signal = filt.generate_signals(bars)
    assert set(signal.unique()) <= {0}  # never even got its first entry through the floor


def test_allows_a_huge_move_through_even_when_price_has_gone_negative():
    # Real event this project's own data contains: crude oil futures traded
    # negative on 2020-04-20. atr is always >= 0, so dividing by a raw
    # negative close used to flip expected_move_frac's sign, making a
    # genuinely enormous move (atr=28 against |close|=37, a ~76% swing)
    # read as a large *negative* fraction - always failing the >= cost-floor
    # check and freezing the position exactly when volatility, and the case
    # for trading through it, was highest.
    prices = [20, 20, 20, 20, 20, 18, -37, -14, 10]
    idx = pd.date_range("2020-04-15", periods=len(prices), freq="1D")
    bars = pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)
    spec = _crypto_spec(commission_pct=0.0005, slippage_pct=0.0)
    filt = CostAwareFilter(Alternating(), spec, atr_period=2, min_cost_multiple=1.0)

    signal = filt.generate_signals(bars)
    raw = Alternating().generate_signals(bars)
    # Once ATR has warmed up, every bar from the crash onward has a real
    # move far exceeding the tiny cost floor, so the filter should track the
    # inner strategy's flips exactly rather than freezing on the negative-
    # close bars.
    assert signal.iloc[5:].tolist() == raw.iloc[5:].tolist()


def test_a_literal_zero_close_blocks_rather_than_force_allows():
    # atr / 0.0 is +inf (not NaN, so plain .fillna(0.0) alone wouldn't catch
    # it) which would otherwise compare as >= any positive threshold and
    # force allowed=True unconditionally - the same "not enough information,
    # so don't override" default as the NaN/warmup case, not an automatic
    # green light.
    prices = [100, 100, 0.0, 100]
    idx = pd.date_range("2026-01-05", periods=len(prices), freq="1min")
    bars = pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)
    spec = _crypto_spec(commission_pct=0.05)  # deliberately huge cost floor
    filt = CostAwareFilter(Alternating(), spec, atr_period=1, min_cost_multiple=1.0)

    signal = filt.generate_signals(bars)
    assert signal.iloc[2] == signal.iloc[1]  # held, not force-allowed


def test_name_delegates_to_inner_strategy():
    spec = _crypto_spec()
    inner = Alternating()
    filt = CostAwareFilter(inner, spec)
    assert filt.name == inner.name
