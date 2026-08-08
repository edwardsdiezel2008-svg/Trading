"""Volatility-based strategies: use the magnitude of recent price movement itself
as the signal, rather than a fixed price level or oscillator threshold."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


class ATRVolatilityBreakout(Strategy):
    """Enters in the direction of a move that exceeds `k` ATRs from the prior
    close - i.e. only trades when volatility itself is expanding, on the
    theory that a large move relative to recent range tends to continue
    short-term. Holds until an opposite-direction breakout. Params: atr_period=14, k=1.5.
    """

    @property
    def name(self) -> str:
        return f"ATR_Vol_Breakout({self.params.get('atr_period', 14)},k={self.params.get('k', 1.5)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        atr_period = self.params.get("atr_period", 14)
        k = self.params.get("k", 1.5)
        close = bars["close"]
        atr = _atr(bars, atr_period)
        move = close.diff()

        raw = pd.Series(np.nan, index=bars.index)
        raw[move > k * atr.shift(1)] = 1
        raw[move < -k * atr.shift(1)] = -1
        signal = raw.ffill().fillna(0)
        signal[atr.isna()] = 0
        return signal
