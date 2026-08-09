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


def test_name_delegates_to_inner_strategy():
    spec = _crypto_spec()
    inner = Alternating()
    filt = CostAwareFilter(inner, spec)
    assert filt.name == inner.name
