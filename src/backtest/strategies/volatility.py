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

    PARAM_SPACE = {"atr_period": [7, 10, 14, 21], "k": [1.0, 1.5, 2.0, 2.5]}

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


class Supertrend(Strategy):
    """The standard Supertrend indicator: upper/lower bands offset from the
    bar's midpoint by `multiplier` ATRs, each ratcheting toward price (never
    away from it) until price closes through the opposite band, at which
    point the trend flips. That ratchet is the key difference from
    ATR_Vol_Breakout's plain single-bar breakout test - the band only ever
    tightens in the trend's favor, so a brief pullback that doesn't actually
    reverse the trend can't flip the signal. This is exactly the kind of
    noise-filtering behavior lower timeframes (e.g. 15-minute bars) need,
    where a one-bar-breakout rule whipsaws on every wiggle.
    Params: atr_period=10, multiplier=3.0.
    """

    PARAM_SPACE = {"atr_period": [7, 10, 14, 21], "multiplier": [1.5, 2.0, 3.0, 4.0]}

    @property
    def name(self) -> str:
        return f"Supertrend({self.params.get('atr_period', 10)},m={self.params.get('multiplier', 3.0)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        atr_period = self.params.get("atr_period", 10)
        multiplier = self.params.get("multiplier", 3.0)
        high, low, close = bars["high"], bars["low"], bars["close"]
        atr = _atr(bars, atr_period)
        hl2 = ((high + low) / 2).to_numpy()
        basic_upper = (hl2 + multiplier * atr.to_numpy())
        basic_lower = (hl2 - multiplier * atr.to_numpy())
        c = close.to_numpy()
        n = len(bars)

        upper = np.full(n, np.nan)
        lower = np.full(n, np.nan)
        trend = np.zeros(n)
        first_valid = None

        for i in range(n):
            if np.isnan(basic_upper[i]) or np.isnan(basic_lower[i]):
                continue
            if first_valid is None:
                first_valid = i
                upper[i] = basic_upper[i]
                lower[i] = basic_lower[i]
                trend[i] = 1 if c[i] >= hl2[i] else -1
                continue
            upper[i] = basic_upper[i] if (basic_upper[i] < upper[i - 1] or c[i - 1] > upper[i - 1]) else upper[i - 1]
            lower[i] = basic_lower[i] if (basic_lower[i] > lower[i - 1] or c[i - 1] < lower[i - 1]) else lower[i - 1]
            if trend[i - 1] == 1 and c[i] < lower[i]:
                trend[i] = -1
            elif trend[i - 1] == -1 and c[i] > upper[i]:
                trend[i] = 1
            else:
                trend[i] = trend[i - 1]

        return pd.Series(trend, index=bars.index)


class KeltnerChannelBreakout(Strategy):
    """Breakout of an EMA-centered, ATR-width channel - a genuinely
    different band construction from both DonchianBreakout (raw N-bar
    high/low, no smoothing) and BollingerReversion (SMA centerline, std-dev
    width): the centerline here reacts faster to recent price than a plain
    SMA, and the band width tracks true range rather than the variance of
    closes, so it doesn't compress as hard in a slow choppy grind. Bands are
    computed from the *prior* bar only (shifted before comparison) so a
    bar's own high/low can't inflate the very channel it's breaking out of -
    the same lookahead guard DonchianBreakout uses.
    Params: period=20 (EMA span), multiplier=2.0 (ATR width), atr_period=14.
    """

    PARAM_SPACE = {"period": [10, 20, 30, 50], "multiplier": [1.5, 2.0, 2.5, 3.0]}

    @property
    def name(self) -> str:
        return f"Keltner_Breakout({self.params.get('period', 20)},m={self.params.get('multiplier', 2.0)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        period = self.params.get("period", 20)
        multiplier = self.params.get("multiplier", 2.0)
        atr_period = self.params.get("atr_period", 14)
        close = bars["close"]
        ema = close.ewm(span=period, adjust=False).mean()
        atr = _atr(bars, atr_period)
        upper = (ema + multiplier * atr).shift(1)
        lower = (ema - multiplier * atr).shift(1)

        raw = pd.Series(np.nan, index=bars.index)
        raw[close > upper] = 1
        raw[close < lower] = -1
        signal = raw.ffill().fillna(0)
        signal[upper.isna()] = 0
        return signal
