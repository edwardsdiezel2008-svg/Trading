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
