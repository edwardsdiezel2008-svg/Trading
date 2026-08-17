"""Trend / momentum strategies: bet that a move continues."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class MovingAverageCrossover(Strategy):
    """Classic dual moving-average trend follower: long when the fast MA is
    above the slow MA, short when it's below. Params: fast=10, slow=50, kind='ema'|'sma'.
    """

    PARAM_SPACE = {"fast": [5, 8, 10, 15, 20], "slow": [30, 40, 50, 75, 100]}

    @property
    def name(self) -> str:
        return f"MA_Crossover({self.params.get('fast', 10)}/{self.params.get('slow', 50)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        fast_n = self.params.get("fast", 10)
        slow_n = self.params.get("slow", 50)
        kind = self.params.get("kind", "ema")
        close = bars["close"]
        if kind == "ema":
            fast = close.ewm(span=fast_n, adjust=False).mean()
            slow = close.ewm(span=slow_n, adjust=False).mean()
        else:
            fast = close.rolling(fast_n).mean()
            slow = close.rolling(slow_n).mean()
        signal = np.where(fast > slow, 1, -1)
        return pd.Series(signal, index=bars.index).where(slow.notna(), 0)


class DonchianBreakout(Strategy):
    """Trades breakouts of the N-bar high/low channel (turtle-style).
    Long on a new N-bar high, short on a new N-bar low, hold until the opposite breakout.
    Params: lookback=20.
    """

    PARAM_SPACE = {"lookback": [10, 15, 20, 30, 40, 55]}

    @property
    def name(self) -> str:
        return f"Donchian_Breakout({self.params.get('lookback', 20)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        n = self.params.get("lookback", 20)
        upper = bars["high"].rolling(n).max()
        lower = bars["low"].rolling(n).min()
        close = bars["close"]

        raw = pd.Series(0, index=bars.index, dtype=float)
        raw[close >= upper.shift(1)] = 1
        raw[close <= lower.shift(1)] = -1
        raw[upper.shift(1).isna()] = np.nan
        # Hold position until the opposite breakout fires.
        signal = raw.replace(0, np.nan).ffill().fillna(0)
        return signal


class MACDMomentum(Strategy):
    """Trades the sign of the MACD histogram (MACD line vs signal line).
    Params: fast=12, slow=26, signal=9.
    """

    PARAM_SPACE = {"fast": [8, 12, 16], "slow": [21, 26, 34], "signal": [6, 9, 12]}

    @property
    def name(self) -> str:
        return f"MACD_Momentum({self.params.get('fast', 12)}/{self.params.get('slow', 26)}/{self.params.get('signal', 9)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        fast_n = self.params.get("fast", 12)
        slow_n = self.params.get("slow", 26)
        signal_n = self.params.get("signal", 9)
        close = bars["close"]
        macd_line = close.ewm(span=fast_n, adjust=False).mean() - close.ewm(span=slow_n, adjust=False).mean()
        signal_line = macd_line.ewm(span=signal_n, adjust=False).mean()
        hist = macd_line - signal_line
        warmup = max(fast_n, slow_n, signal_n)
        signal = pd.Series(np.where(hist > 0, 1, -1), index=bars.index)
        signal.iloc[:warmup] = 0
        return signal


class ParabolicSAR(Strategy):
    """Wilder's Parabolic SAR: a trailing stop-and-reverse level that
    accelerates toward price the longer the current trend runs, flipping
    the position the instant price trades through it. The ratchet here is
    driven by an acceleration factor that increments every time a new trend
    extreme prints and resets on every flip - a fundamentally different
    mechanism from Supertrend's ATR-width bands (which ratchet on
    volatility, not on how long the trend has already run), so the two
    don't just converge to relabeled versions of the same signal.
    Params: af_start=0.02 (initial/reset acceleration), af_step=af_start
    (increment per new extreme), af_max=0.2 (acceleration ceiling).
    """

    PARAM_SPACE = {"af_start": [0.01, 0.02, 0.03], "af_max": [0.1, 0.2, 0.3, 0.4]}

    @property
    def name(self) -> str:
        return f"Parabolic_SAR(af={self.params.get('af_start', 0.02)},max={self.params.get('af_max', 0.2)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        af_start = self.params.get("af_start", 0.02)
        af_step = self.params.get("af_step", af_start)
        af_max = self.params.get("af_max", 0.2)
        high, low, close = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
        n = len(bars)
        trend = np.zeros(n)
        if n < 2:
            return pd.Series(trend, index=bars.index)

        sar = np.zeros(n)
        uptrend = close[1] >= close[0]
        sar[1] = low[0] if uptrend else high[0]
        ep = high[1] if uptrend else low[1]
        af = af_start
        trend[1] = 1 if uptrend else -1

        for i in range(2, n):
            candidate = sar[i - 1] + af * (ep - sar[i - 1])
            if uptrend:
                candidate = min(candidate, low[i - 1], low[i - 2])
                if low[i] < candidate:
                    uptrend = False
                    sar[i] = ep
                    ep = low[i]
                    af = af_start
                else:
                    sar[i] = candidate
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + af_step, af_max)
            else:
                candidate = max(candidate, high[i - 1], high[i - 2])
                if high[i] > candidate:
                    uptrend = True
                    sar[i] = ep
                    ep = high[i]
                    af = af_start
                else:
                    sar[i] = candidate
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + af_step, af_max)
            trend[i] = 1 if uptrend else -1

        return pd.Series(trend, index=bars.index)
