"""Volume Profile and TPO (Time Price Opportunity / Market Profile) strategies:
bet that price reverts to the price level where the real activity happened,
rather than to a moving average or a fixed-lookback high/low band.

Both build a rolling horizontal histogram of price levels over the prior
`lookback` bars, then derive a Point of Control (POC - the single busiest
level) and a Value Area (the tightest band containing `value_area_pct` of
the histogram's total weight, bounded by VAH/VAL). Price trading outside
the value area is read as "away from fair value" and long/short accordingly;
it flattens the instant price re-enters the value area.

The two strategies differ only in what "busiest" means, which is the real,
substantive distinction between Volume Profile and Market Profile in
practice - not a relabeled duplicate:
- VolumeProfileReversion weights each bar's contribution by its *volume*
  (so one large print can dominate a level).
- TPOReversion instead counts, for each fixed-length time period (a "TPO
  period" - several consecutive bars), whether that period's range touched
  a level at all - one vote per period regardless of how much size traded,
  so a level visited by many separate periods outranks one hit hard by a
  single burst.

Both are built from strictly prior bars (the lookback window ends the bar
before the signal bar), so the level being tested can't be inflated by the
very bar being compared against it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _value_area(weight_per_bin: np.ndarray, bin_edges: np.ndarray, value_area_pct: float):
    total = weight_per_bin.sum()
    if total <= 0:
        return np.nan, np.nan, np.nan
    poc_bin = int(np.argmax(weight_per_bin))
    poc_price = (bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2
    order = np.argsort(weight_per_bin)[::-1]
    cum = 0.0
    lo_bin, hi_bin = poc_bin, poc_bin
    for b in order:
        cum += weight_per_bin[b]
        lo_bin, hi_bin = min(lo_bin, b), max(hi_bin, b)
        if cum >= value_area_pct * total:
            break
    return poc_price, bin_edges[lo_bin], bin_edges[hi_bin + 1]


class VolumeProfileReversion(Strategy):
    """Rolling volume profile reversion: bins the prior `lookback` bars'
    volume by price (each bar's volume assigned to the bin containing its
    high-low midpoint), finds the Point of Control and Value Area from that
    histogram, and trades reversion toward it. Long when price closes below
    the Value Area Low, short when above the Value Area High, flat once it
    re-enters the value area.
    Params: lookback=30, num_bins=24 (fixed), value_area_pct=0.7 (fixed).
    """

    PARAM_SPACE = {"lookback": [20, 30, 50, 80]}

    @property
    def name(self) -> str:
        return f"VolProfile_Reversion({self.params.get('lookback', 30)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        lookback = self.params.get("lookback", 30)
        num_bins = self.params.get("num_bins", 24)
        value_area_pct = self.params.get("value_area_pct", 0.7)
        high = bars["high"].to_numpy()
        low = bars["low"].to_numpy()
        close = bars["close"].to_numpy()
        volume = bars["volume"].to_numpy()
        mid = (high + low) / 2.0
        n = len(bars)
        signal = np.zeros(n)

        for i in range(lookback, n):
            w_lo, w_hi = i - lookback, i
            price_min = low[w_lo:w_hi].min()
            price_max = high[w_lo:w_hi].max()
            if price_max <= price_min:
                continue
            bin_edges = np.linspace(price_min, price_max, num_bins + 1)
            bin_idx = np.clip(np.digitize(mid[w_lo:w_hi], bin_edges) - 1, 0, num_bins - 1)
            vol_per_bin = np.zeros(num_bins)
            np.add.at(vol_per_bin, bin_idx, volume[w_lo:w_hi])
            _, val_low, val_high = _value_area(vol_per_bin, bin_edges, value_area_pct)
            if np.isnan(val_low):
                continue
            if close[i] < val_low:
                signal[i] = 1
            elif close[i] > val_high:
                signal[i] = -1
            else:
                signal[i] = 0

        return pd.Series(signal, index=bars.index)


class TPOReversion(Strategy):
    """Rolling TPO (Time Price Opportunity) reversion: splits the prior
    `lookback` bars into fixed-length time periods (`period_bars` bars
    each - the TPO "letters"), and for each period marks every price bin
    its high-low range touched, incrementing that bin's count by exactly 1
    regardless of volume or how many sub-bars touched it. The Point of
    Control and Value Area come from that period-presence histogram, not a
    volume histogram - a level visited by many separate periods outranks
    one hit hard by a single volume burst, which is the actual point of
    Market Profile over Volume Profile. Long when price closes below the
    Value Area Low, short when above the Value Area High, flat once it
    re-enters the value area.
    Params: lookback=60, period_bars=5 (bars per TPO period), num_bins=24 (fixed).
    """

    PARAM_SPACE = {"lookback": [40, 80], "period_bars": [4, 8]}

    @property
    def name(self) -> str:
        return f"TPO_Reversion({self.params.get('lookback', 60)},p={self.params.get('period_bars', 5)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        lookback = self.params.get("lookback", 60)
        period_bars = self.params.get("period_bars", 5)
        num_bins = self.params.get("num_bins", 24)
        value_area_pct = self.params.get("value_area_pct", 0.7)
        high = bars["high"].to_numpy()
        low = bars["low"].to_numpy()
        close = bars["close"].to_numpy()
        n = len(bars)
        signal = np.zeros(n)

        for i in range(lookback, n):
            w_lo, w_hi = i - lookback, i
            w_high, w_low = high[w_lo:w_hi], low[w_lo:w_hi]
            price_min = w_low.min()
            price_max = w_high.max()
            if price_max <= price_min:
                continue
            bin_edges = np.linspace(price_min, price_max, num_bins + 1)
            count_per_bin = np.zeros(num_bins)
            window_len = w_hi - w_lo
            for p_start in range(0, window_len, period_bars):
                p_end = min(p_start + period_bars, window_len)
                period_high = w_high[p_start:p_end].max()
                period_low = w_low[p_start:p_end].min()
                lo_bin = int(np.clip(np.digitize(period_low, bin_edges) - 1, 0, num_bins - 1))
                hi_bin = int(np.clip(np.digitize(period_high, bin_edges) - 1, 0, num_bins - 1))
                count_per_bin[lo_bin:hi_bin + 1] += 1
            _, val_low, val_high = _value_area(count_per_bin, bin_edges, value_area_pct)
            if np.isnan(val_low):
                continue
            if close[i] < val_low:
                signal[i] = 1
            elif close[i] > val_high:
                signal[i] = -1
            else:
                signal[i] = 0

        return pd.Series(signal, index=bars.index)
