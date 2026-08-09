"""Mean-reversion strategies: bet that an extended move snaps back to a baseline."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class RSIReversion(Strategy):
    """Long when RSI is oversold, short when overbought, flat/exit back through
    the midline. Params: period=14, lower=30, upper=70.
    """

    PARAM_SPACE = {"period": [7, 10, 14, 21], "lower": [20, 25, 30], "upper": [70, 75, 80]}

    @property
    def name(self) -> str:
        return f"RSI_Reversion({self.params.get('period', 14)},{self.params.get('lower', 30)}/{self.params.get('upper', 70)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        period = self.params.get("period", 14)
        lower = self.params.get("lower", 30)
        upper = self.params.get("upper", 70)
        rsi = _rsi(bars["close"], period)

        raw = pd.Series(np.nan, index=bars.index)
        raw[rsi <= lower] = 1
        raw[rsi >= upper] = -1
        raw[(rsi > lower) & (rsi < upper) & (rsi.shift(1) <= lower)] = 0
        raw[(rsi > lower) & (rsi < upper) & (rsi.shift(1) >= upper)] = 0
        return raw.ffill().fillna(0)


class BollingerReversion(Strategy):
    """Long when price closes below the lower Bollinger Band, short when above
    the upper band, exit at the midline (moving average). Params: period=20, num_std=2.
    """

    PARAM_SPACE = {"period": [10, 15, 20, 30], "num_std": [1.5, 2.0, 2.5]}

    @property
    def name(self) -> str:
        return f"Bollinger_Reversion({self.params.get('period', 20)},{self.params.get('num_std', 2)}sd)"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        period = self.params.get("period", 20)
        num_std = self.params.get("num_std", 2)
        close = bars["close"]
        mid = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = mid + num_std * std
        lower = mid - num_std * std

        raw = pd.Series(np.nan, index=bars.index)
        raw[close <= lower] = 1
        raw[close >= upper] = -1
        crossed_back_up = (close > mid) & (close.shift(1) <= mid)
        crossed_back_down = (close < mid) & (close.shift(1) >= mid)
        raw[crossed_back_up | crossed_back_down] = 0
        signal = raw.ffill().fillna(0)
        signal[mid.isna()] = 0
        return signal


class ZScoreReversion(Strategy):
    """Trades the standardized distance of price from its rolling mean:
    long when the z-score is below -entry_z, short when above +entry_z,
    exits when it reverts inside +/-exit_z. Params: period=20, entry_z=2.0, exit_z=0.5.
    """

    PARAM_SPACE = {"period": [10, 15, 20, 30], "entry_z": [1.5, 2.0, 2.5]}

    @property
    def name(self) -> str:
        return f"ZScore_Reversion({self.params.get('period', 20)},z={self.params.get('entry_z', 2.0)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        period = self.params.get("period", 20)
        entry_z = self.params.get("entry_z", 2.0)
        exit_z = self.params.get("exit_z", 0.5)
        close = bars["close"]
        mean = close.rolling(period).mean()
        std = close.rolling(period).std()
        z = (close - mean) / std.replace(0, np.nan)

        raw = pd.Series(np.nan, index=bars.index)
        raw[z <= -entry_z] = 1
        raw[z >= entry_z] = -1
        raw[z.abs() <= exit_z] = 0
        signal = raw.ffill().fillna(0)
        signal[z.isna()] = 0
        return signal


class VWAPReversion(Strategy):
    """Mean-reversion around a rolling volume-weighted average price, rather
    than a simple/exponential moving average of price alone - the one
    strategy in this library that actually uses the bar's volume column.
    Long when price is more than entry_pct below rolling VWAP, short when
    that far above, flat once it reverts within exit_pct. VWAP is a
    standard intraday fair-value anchor (institutional execution
    benchmarks are built around it) precisely because it weights the
    moves that came with size more than ones that didn't.
    Params: window=20, entry_pct=0.02, exit_pct=0.005.
    """

    PARAM_SPACE = {"window": [10, 14, 20, 30], "entry_pct": [0.01, 0.02, 0.03, 0.05]}

    @property
    def name(self) -> str:
        return f"VWAP_Reversion({self.params.get('window', 20)},{self.params.get('entry_pct', 0.02) * 100:.0f}%)"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        window = self.params.get("window", 20)
        entry_pct = self.params.get("entry_pct", 0.02)
        exit_pct = self.params.get("exit_pct", 0.005)
        close, volume = bars["close"], bars["volume"]
        typical = (bars["high"] + bars["low"] + bars["close"]) / 3
        pv_sum = (typical * volume).rolling(window).sum()
        vol_sum = volume.rolling(window).sum().replace(0, np.nan)
        vwap = pv_sum / vol_sum
        dist = (close - vwap) / vwap

        raw = pd.Series(np.nan, index=bars.index)
        raw[dist <= -entry_pct] = 1
        raw[dist >= entry_pct] = -1
        raw[dist.abs() <= exit_pct] = 0
        signal = raw.ffill().fillna(0)
        signal[vwap.isna()] = 0
        return signal
