"""Volume confirmation filter: wraps any Strategy and suppresses opening a
new position unless the current bar's volume clears a multiple of its own
recent rolling average.

The idea traders commonly cite for breakout patterns specifically: a
breakout on below-average volume reflects less real participation than one
that clears convincingly. Unlike CostAwareFilter (which blocks *every*
position change, entry or exit, when the expected move can't cover costs),
this only gates NEW entries - a transition away from flat. An exit back to
flat is never blocked on volume, since staying trapped in a position because
volume happens to be thin on the bar you wanted to leave is a risk-
management problem, not a signal-quality one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy
from .patterns import InsideBarBreakout


class VolumeConfirmationFilter(Strategy):
    """Delegates signal generation to `inner`; suppresses opening a new
    position (any transition away from flat) unless the bar's volume is at
    least `min_volume_multiple` times its own `volume_period`-bar rolling
    average. Exits back to flat always pass through unfiltered."""

    def __init__(self, inner: Strategy, volume_period: int = 20, min_volume_multiple: float = 1.0):
        super().__init__(params={})
        self.inner = inner
        self.volume_period = volume_period
        self.min_volume_multiple = min_volume_multiple

    @property
    def name(self) -> str:
        return f"{self.inner.name}+Vol{self.min_volume_multiple:g}x"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        raw = self.inner.generate_signals(bars).reindex(bars.index).fillna(0)
        avg_volume = bars["volume"].rolling(self.volume_period).mean()
        confirmed = (bars["volume"] >= self.min_volume_multiple * avg_volume).fillna(False).to_numpy()

        raw_vals = raw.to_numpy()
        out = np.empty(len(bars))
        prev = 0.0
        for i in range(len(bars)):
            want = raw_vals[i]
            opening_new_position = want != prev and want != 0
            if opening_new_position and not confirmed[i]:
                want = prev
            out[i] = want
            prev = want
        return pd.Series(out, index=bars.index)


class InsideBarBreakoutVolumeConfirmed(Strategy):
    """InsideBarBreakout, but a new entry only fires if the breakout bar's
    volume clears a multiple of its own recent 20-bar rolling average - a
    real, walk-forward-testable version of the "volume confirms a breakout"
    idea traders commonly cite, rather than taking it on faith. Not part of
    ALL_STRATEGY_CLASSES - a standalone research variant, run and reported
    on deliberately rather than folded into every track's snapshot."""

    PARAM_SPACE = {"max_range_ratio": [0.3, 0.5, 0.6, 0.8], "min_volume_multiple": [1.0, 1.2, 1.5]}

    @property
    def name(self) -> str:
        ratio = self.params.get("max_range_ratio", 0.6)
        mult = self.params.get("min_volume_multiple", 1.0)
        return f"Inside_Bar_Breakout_VolConfirmed({ratio:.1f},{mult:g}x)"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        inner = InsideBarBreakout(params={"max_range_ratio": self.params.get("max_range_ratio", 0.6)})
        filt = VolumeConfirmationFilter(inner, volume_period=20, min_volume_multiple=self.params.get("min_volume_multiple", 1.0))
        return filt.generate_signals(bars)
