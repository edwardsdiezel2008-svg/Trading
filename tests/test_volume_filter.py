import pandas as pd

from src.backtest.strategies.base import Strategy
from src.backtest.strategies.volume_filter import VolumeConfirmationFilter


class FixedSignal(Strategy):
    """Replays an exact, pre-chosen signal sequence - lets a test control
    precisely which bar wants to open/close/flip a position."""

    def __init__(self, signals):
        super().__init__(params={})
        self._signals = signals

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(self._signals, index=bars.index)


def _bars(volumes, prices=None):
    n = len(volumes)
    prices = prices if prices is not None else [100] * n
    idx = pd.date_range("2026-01-05", periods=n, freq="5min")
    return pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": volumes}, index=idx
    )


def test_blocks_new_entry_on_below_average_volume():
    # Rolling 3-bar average volume warms up over bars 0-2 (~100 each); bar 3
    # wants to open a long position but only has volume 20, well under the
    # 1.0x-average threshold - the entry should be suppressed at that bar,
    # even though the still-pending "want=1" signal is free to go through
    # on a later bar once the rolling average recovers enough to confirm it.
    volumes = [100, 100, 100, 20, 100, 100]
    signals = [0, 0, 0, 1, 1, 1]
    bars = _bars(volumes)
    filt = VolumeConfirmationFilter(FixedSignal(signals), volume_period=3, min_volume_multiple=1.0)
    out = filt.generate_signals(bars)
    assert out.iloc[3] == 0  # blocked at the low-volume bar itself


def test_allows_new_entry_on_above_average_volume():
    volumes = [100, 100, 100, 400, 100, 100]
    signals = [0, 0, 0, 1, 1, 1]
    bars = _bars(volumes)
    filt = VolumeConfirmationFilter(FixedSignal(signals), volume_period=3, min_volume_multiple=1.0)
    out = filt.generate_signals(bars)
    assert out.iloc[3] == 1  # confirmed - entry passes through
    assert out.tolist() == [0, 0, 0, 1, 1, 1]


def test_exit_to_flat_always_passes_regardless_of_volume():
    # Enters on bar 3 (high volume), then the inner strategy wants flat on
    # bar 4 while volume is thin - the exit must still go through.
    volumes = [100, 100, 100, 400, 10, 10]
    signals = [0, 0, 0, 1, 0, 0]
    bars = _bars(volumes)
    filt = VolumeConfirmationFilter(FixedSignal(signals), volume_period=3, min_volume_multiple=1.0)
    out = filt.generate_signals(bars)
    assert out.tolist() == [0, 0, 0, 1, 0, 0]


def test_direction_flip_is_treated_as_a_new_entry_and_can_be_blocked():
    # Already long from bar 3; bar 4 wants to flip straight to short on thin
    # volume - that flip is a new (short) position and should be blocked,
    # holding the prior long position instead of flattening or flipping.
    volumes = [100, 100, 100, 400, 10, 10]
    signals = [0, 0, 0, 1, -1, -1]
    bars = _bars(volumes)
    filt = VolumeConfirmationFilter(FixedSignal(signals), volume_period=3, min_volume_multiple=1.0)
    out = filt.generate_signals(bars)
    assert out.tolist() == [0, 0, 0, 1, 1, 1]


def test_name_shows_inner_name_and_multiple():
    filt = VolumeConfirmationFilter(FixedSignal([0]), min_volume_multiple=1.5)
    assert "Vol1.5x" in filt.name


def _pattern_bars(breakout_volume, n_warmup=20):
    """n_warmup flat bars (steady volume, no signal) then a mother bar, an
    inside bar consolidating within it, and a breakout bar that closes above
    the mother bar's high - the exact setup InsideBarBreakout needs to fire
    a long entry, with breakout_volume controlling whether that entry clears
    the wrapper's volume confirmation."""
    from src.backtest.strategies.volume_filter import InsideBarBreakoutVolumeConfirmed

    warmup_close = [100.0] * n_warmup
    closes = warmup_close + [100.0, 100.5, 115.0]  # mother, inside, breakout
    highs = [100.5] * n_warmup + [110.0, 102.0, 115.0]
    lows = [99.5] * n_warmup + [90.0, 98.0, 114.0]
    volumes = [100.0] * n_warmup + [100.0, 100.0, breakout_volume]
    idx = pd.date_range("2026-01-05", periods=len(closes), freq="5min")
    bars = pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes}, index=idx
    )
    return bars, InsideBarBreakoutVolumeConfirmed


def test_inside_bar_breakout_volume_confirmed_fires_on_a_confirmed_breakout():
    bars, cls = _pattern_bars(breakout_volume=500.0)
    strat = cls(params={"max_range_ratio": 0.6, "min_volume_multiple": 1.0})
    out = strat.generate_signals(bars)
    assert out.iloc[-1] == 1  # high volume clears the 1.0x average - entry passes through


def test_inside_bar_breakout_volume_confirmed_blocks_on_thin_breakout_volume():
    bars, cls = _pattern_bars(breakout_volume=10.0)
    strat = cls(params={"max_range_ratio": 0.6, "min_volume_multiple": 1.0})
    out = strat.generate_signals(bars)
    assert out.iloc[-1] == 0  # thin volume - the breakout is suppressed, stays flat


def test_inside_bar_breakout_volume_confirmed_name_reflects_its_params():
    from src.backtest.strategies.volume_filter import InsideBarBreakoutVolumeConfirmed

    strat = InsideBarBreakoutVolumeConfirmed(params={"max_range_ratio": 0.5, "min_volume_multiple": 1.5})
    assert strat.name == "Inside_Bar_Breakout_VolConfirmed(0.5,1.5x)"


def test_inside_bar_breakout_volume_confirmed_name_defaults_when_params_missing():
    from src.backtest.strategies.volume_filter import InsideBarBreakoutVolumeConfirmed

    strat = InsideBarBreakoutVolumeConfirmed(params={})
    assert strat.name == "Inside_Bar_Breakout_VolConfirmed(0.6,1x)"
