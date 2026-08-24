"""Cost-aware trade filter: wraps any Strategy and suppresses position
changes when the recent expected move (ATR as a fraction of price) can't
plausibly clear round-trip transaction costs by a safety margin.

Built for the 15-minute BTC track: strategies here use the same
default parameters as the daily track (e.g. MA_Crossover(10/50) means a
10-bar/50-bar average either way), which on 15-minute bars is a
2.5-hour/12.5-hour lookback instead of a 10-day/50-day one - far shorter,
so price noise crosses those averages constantly. Every crossing is a real
trade at the same fixed percentage cost regardless of timeframe, and the
typical 15-minute move is nowhere near big enough to clear that cost
repeatedly. This filter doesn't change what a strategy *wants* to do, it
just skips acting on that signal when the bar's own recent volatility says
the expected move is too small to be worth paying for - the strategy holds
its current position instead of flipping.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _true_range(bars: pd.DataFrame) -> pd.Series:
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


class CostAwareFilter(Strategy):
    """Delegates signal generation to `inner`; on any bar where inner wants
    to change position, holds the prior position instead if the ATR-based
    expected move is smaller than `min_cost_multiple` times the round-trip
    transaction cost (spec's commission_pct + slippage_pct, charged on both
    entry and exit)."""

    def __init__(self, inner: Strategy, spec, atr_period: int = 14, min_cost_multiple: float = 3.0):
        super().__init__(params={})
        self.inner = inner
        self.spec = spec
        self.atr_period = atr_period
        self.min_cost_multiple = min_cost_multiple

    @property
    def name(self) -> str:
        return self.inner.name

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        raw = self.inner.generate_signals(bars).reindex(bars.index).fillna(0)
        atr = _true_range(bars).ewm(alpha=1 / self.atr_period, adjust=False, min_periods=self.atr_period).mean()
        round_trip_cost_frac = 2 * (self.spec.commission_pct + self.spec.slippage_pct)
        # abs(close): a handful of instruments this project tracks (crude oil
        # futures went negative in April 2020) can have a non-positive price.
        # atr is always >= 0, so dividing by a raw negative close flips the
        # sign and makes a huge real move read as a large *negative* fraction
        # - always failing the >= threshold below and freezing the position
        # exactly when volatility (and the case for trading through it) is
        # highest. Using the price's magnitude keeps this a measure of "how
        # big is the move relative to the price level" regardless of sign.
        # replace(inf, nan) then fillna(0.0) covers a literal 0.0 close the
        # same way an unwarmed-up (NaN) atr already is: no signal either way
        # about whether the move clears the cost floor, so default to
        # blocking (holding the prior position) rather than dividing by zero
        # into +inf, which would otherwise force allowed=True unconditionally.
        expected_move_frac = (atr / bars["close"].abs()).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        allowed = (expected_move_frac >= self.min_cost_multiple * round_trip_cost_frac).to_numpy()

        raw_vals = raw.to_numpy()
        out = np.empty(len(bars))
        prev = 0.0
        for i in range(len(bars)):
            want = raw_vals[i]
            if want != prev and not allowed[i]:
                want = prev
            out[i] = want
            prev = want
        return pd.Series(out, index=bars.index)
