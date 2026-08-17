"""Auction Market Theory strategy: multi-timeframe volume profile + VWAP.

Stacks reference levels from three timeframes at once - the prior session,
the prior week (5 sessions), and the prior month (21 sessions) - plus a live
intrasession VWAP with standard-deviation bands. This mirrors how
discretionary Market Profile / Auction Market Theory traders build a level
map before the session: higher-timeframe context first, then the current
session's live read.

Two setups, both requiring multi-timeframe agreement:

  * Fade at confluence: price is inside the prior session's value area
    (balance) and returns to a value-area edge that the week and/or month
    profile also mark as a level (within `confluence_points`) - counter-trend
    entry back toward the session VWAP.
  * Breakout with the trend: price closes outside the prior session's value
    area (imbalance) *and* session VWAP confirms (price is on the same side
    of VWAP as the breakout) - trade with the break.

Exit is at session VWAP (the fade/breakout has resolved back to "fair value")
or on an opposing signal.

Volume-at-price is approximated from OHLCV bars (no tick data available) by
distributing each bar's volume evenly across the price bins its high-low
range overlaps - a standard approximation when only bar data is on hand.
"Poor" highs/lows (unfinished auctions, per TPO theory) are approximated as
session extremes touched by more than one bar, since intraday bars are
themselves discrete "time at price" units.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _volume_profile_hist(bars: pd.DataFrame, bin_edges: np.ndarray) -> np.ndarray:
    """Distribute each bar's volume across the price bins its high-low range
    overlaps. Returns a histogram aligned to bin_edges (len = len(bin_edges)-1).
    """
    n_bins = len(bin_edges) - 1
    hist = np.zeros(n_bins)
    if bars.empty:
        return hist
    lo = bars["low"].to_numpy()
    hi = bars["high"].to_numpy()
    vol = bars["volume"].to_numpy()
    bin_lo = np.clip(np.searchsorted(bin_edges, lo, side="right") - 1, 0, n_bins - 1)
    bin_hi = np.clip(np.searchsorted(bin_edges, hi, side="right") - 1, 0, n_bins - 1)
    for i in range(len(bars)):
        a, b = int(bin_lo[i]), int(bin_hi[i])
        if b < a:
            a, b = b, a
        span = b - a + 1
        hist[a:b + 1] += vol[i] / span
    return hist


def _profile_levels(hist: np.ndarray, bin_mids: np.ndarray, va_pct: float = 0.70):
    """POC / value-area-high / value-area-low from a volume-at-price histogram."""
    total = hist.sum()
    if total <= 0:
        return np.nan, np.nan, np.nan
    poc_idx = int(np.argmax(hist))
    target = total * va_pct
    lo_idx = hi_idx = poc_idx
    covered = hist[poc_idx]
    while covered < target and (lo_idx > 0 or hi_idx < len(hist) - 1):
        left = hist[lo_idx - 1] if lo_idx > 0 else -1.0
        right = hist[hi_idx + 1] if hi_idx < len(hist) - 1 else -1.0
        if right >= left:
            hi_idx += 1
            covered += hist[hi_idx]
        else:
            lo_idx -= 1
            covered += hist[lo_idx]
    return bin_mids[poc_idx], bin_mids[hi_idx], bin_mids[lo_idx]


def _session_vwap_and_std(bars: pd.DataFrame, session_id: pd.Series) -> tuple[pd.Series, pd.Series]:
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    vol = bars["volume"].clip(lower=1e-9)  # avoid div-by-zero on zero-volume bars
    grouped_pv = (typical * vol).groupby(session_id).cumsum()
    grouped_vol = vol.groupby(session_id).cumsum()
    vwap = grouped_pv / grouped_vol
    sq_dev = ((typical - vwap) ** 2 * vol).groupby(session_id).cumsum()
    variance = sq_dev / grouped_vol
    std = np.sqrt(variance.clip(lower=0))
    return vwap, std


def _build_session_table(bars: pd.DataFrame, session_id: pd.Series, bin_edges: np.ndarray, bin_mids: np.ndarray, va_pct: float) -> pd.DataFrame:
    """One row per session: POC/VAH/VAL for that session alone, plus the
    session's own high/low and whether those extremes were touched by more
    than one bar ("poor" = unfinished auction, a magnet for future price).
    """
    rows = []
    session_dates = []
    for date, sub in bars.groupby(session_id):
        hist = _volume_profile_hist(sub, bin_edges)
        poc, vah, val = _profile_levels(hist, bin_mids, va_pct)
        s_high, s_low = sub["high"].max(), sub["low"].min()
        poor_high = (sub["high"] >= s_high).sum() > 1
        poor_low = (sub["low"] <= s_low).sum() > 1
        rows.append({
            "poc": poc, "vah": vah, "val": val,
            "session_high": s_high, "session_low": s_low,
            "poor_high": poor_high, "poor_low": poor_low,
            "hist": hist,
        })
        session_dates.append(date)
    return pd.DataFrame(rows, index=pd.Index(session_dates, name="session"))


def _rolling_period_levels(session_table: pd.DataFrame, window: int, bin_mids: np.ndarray, va_pct: float) -> pd.DataFrame:
    """Combine `window` prior (completed) sessions' histograms into one
    composite volume profile per session - approximates a weekly/monthly
    profile from daily session histograms.
    """
    hists = np.stack(session_table["hist"].to_numpy())
    n = len(session_table)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    for i in range(n):
        start = max(0, i - window)
        end = i  # excludes current session - prior sessions only
        if end <= start:
            continue
        combined = hists[start:end].sum(axis=0)
        poc[i], vah[i], val[i] = _profile_levels(combined, bin_mids, va_pct)
    return pd.DataFrame({"poc": poc, "vah": vah, "val": val}, index=session_table.index)


class AuctionMarketProfileStrategy(Strategy):
    """Multi-timeframe Auction Market Theory strategy - see module docstring.

    Params: bins=100, va_pct=0.70, confluence_points=8.0, week_sessions=5,
    month_sessions=21.
    """

    PARAM_SPACE = {"bins": [60, 100, 150], "confluence_points": [4.0, 8.0, 16.0]}

    @property
    def name(self) -> str:
        return f"AuctionMarketProfile(bins={self.params.get('bins', 100)},conf={self.params.get('confluence_points', 8.0)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        bins = int(self.params.get("bins", 100))
        va_pct = float(self.params.get("va_pct", 0.70))
        conf = float(self.params.get("confluence_points", 8.0))
        week_n = int(self.params.get("week_sessions", 5))
        month_n = int(self.params.get("month_sessions", 21))

        if len(bars) < 50:
            return pd.Series(0, index=bars.index)

        session_id = pd.Series(bars.index.normalize(), index=bars.index)

        price_min, price_max = bars["low"].min(), bars["high"].max()
        bin_edges = np.linspace(price_min, price_max, bins + 1)
        bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2

        session_table = _build_session_table(bars, session_id, bin_edges, bin_mids, va_pct)
        week_table = _rolling_period_levels(session_table, week_n, bin_mids, va_pct)
        month_table = _rolling_period_levels(session_table, month_n, bin_mids, va_pct)

        # Reference levels for "today" must come from *completed prior*
        # sessions only - shift the whole session-level table forward by one.
        prior_sess = session_table.shift(1)
        prior_week = week_table.shift(1)
        prior_month = month_table.shift(1)

        def broadcast(col: pd.Series) -> pd.Series:
            return session_id.map(col)

        p_poc = broadcast(prior_sess["poc"])
        p_vah = broadcast(prior_sess["vah"])
        p_val = broadcast(prior_sess["val"])
        w_vah = broadcast(prior_week["vah"])
        w_val = broadcast(prior_week["val"])
        m_vah = broadcast(prior_month["vah"])
        m_val = broadcast(prior_month["val"])

        vwap, vwap_std = _session_vwap_and_std(bars, session_id)

        close = bars["close"]

        confluence_support = ((p_val - w_val).abs() <= conf) | ((p_val - m_val).abs() <= conf)
        confluence_resistance = ((p_vah - w_vah).abs() <= conf) | ((p_vah - m_vah).abs() <= conf)

        balanced = (close >= p_val) & (close <= p_vah)
        near_support = (close - p_val).abs() <= conf
        near_resistance = (close - p_vah).abs() <= conf

        fade_long = balanced & near_support & confluence_support & (close > vwap - vwap_std)
        fade_short = balanced & near_resistance & confluence_resistance & (close < vwap + vwap_std)

        breakout_long = (close > p_vah) & (close > vwap)
        breakout_short = (close < p_val) & (close < vwap)

        exit_long_at_vwap = close >= vwap
        exit_short_at_vwap = close <= vwap

        has_levels = p_vah.notna() & p_val.notna()

        raw = pd.Series(np.nan, index=bars.index)
        raw[fade_long | breakout_long] = 1
        raw[fade_short | breakout_short] = -1
        signal = raw.ffill().fillna(0)

        # Flatten a long once price has reverted (or run) back to VWAP, and
        # symmetrically for shorts - both setups target "back to fair value."
        was_long = signal.shift(1) == 1
        was_short = signal.shift(1) == -1
        signal[was_long & exit_long_at_vwap & ~(fade_long | breakout_long)] = 0
        signal = signal.ffill()
        was_short2 = signal.shift(1) == -1
        signal[was_short2 & exit_short_at_vwap & ~(fade_short | breakout_short)] = 0
        signal = signal.ffill().fillna(0)

        signal[~has_levels] = 0
        return signal
