"""Candlestick / price-action pattern-recognition strategies.

Unlike the indicator-based strategies elsewhere in this package (moving
averages, RSI, MACD, etc.), these read the raw shape of one or two bars at a
time - the kind of setup traders describe as "reading the candles" rather
than "reading an indicator." All three are standard, widely documented
setups (see the Learn page for sources), chosen specifically because they
translate cleanly to intraday timeframes: a 5-minute chart shows far more
candlestick patterns per session than a daily chart does, so this is where
"pattern recognition" strategies earn their keep.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class EngulfingReversal(Strategy):
    """Classic two-candle reversal: a bullish engulfing candle (a green
    candle whose body fully engulfs the prior red candle's body) after a
    down move signals a long reversal; a bearish engulfing candle signals
    short. Holds until the opposite pattern fires.
    Params: min_body_pct=0.3 - the engulfing candle's own body must be at
    least this fraction of its high-low range, filtering out weak/doji-like
    candles that technically engulf the prior body but carry little
    conviction behind the move.
    """

    PARAM_SPACE = {"min_body_pct": [0.1, 0.2, 0.3, 0.5]}

    @property
    def name(self) -> str:
        return f"Engulfing_Reversal({self.params.get('min_body_pct', 0.3):.1f})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        min_body_pct = self.params.get("min_body_pct", 0.3)
        o, h, l, c = bars["open"], bars["high"], bars["low"], bars["close"]
        prior_o, prior_c = o.shift(1), c.shift(1)

        body = (c - o).abs()
        rng = (h - l).replace(0, np.nan)
        strong_body = (body / rng) >= min_body_pct

        prior_red = prior_c < prior_o
        prior_green = prior_c > prior_o
        curr_green = c > o
        curr_red = c < o

        bullish_engulf = prior_red & curr_green & (o <= prior_c) & (c >= prior_o) & strong_body
        bearish_engulf = prior_green & curr_red & (o >= prior_c) & (c <= prior_o) & strong_body

        raw = pd.Series(np.nan, index=bars.index)
        raw[bullish_engulf] = 1
        raw[bearish_engulf] = -1
        return raw.ffill().fillna(0)


class InsideBarBreakout(Strategy):
    """Consolidation-then-breakout: an 'inside bar' (a bar whose entire
    high-low range sits inside the prior 'mother' bar's range, marking a
    pause) followed by a breakout of the mother bar's high or low. Long on
    a close above the mother bar's high, short on a close below its low.
    Params: max_range_ratio=0.6 - the inside bar's range must be no more
    than this fraction of the mother bar's range; tighter consolidation
    (a lower ratio) means more conviction behind the eventual breakout.
    """

    PARAM_SPACE = {"max_range_ratio": [0.3, 0.5, 0.6, 0.8]}

    @property
    def name(self) -> str:
        return f"Inside_Bar_Breakout({self.params.get('max_range_ratio', 0.6):.1f})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        max_range_ratio = self.params.get("max_range_ratio", 0.6)
        h, l, c = bars["high"], bars["low"], bars["close"]
        mother_high, mother_low = h.shift(1), l.shift(1)
        mother_range = (mother_high - mother_low).replace(0, np.nan)
        inside_range = h - l
        is_inside = (h < mother_high) & (l > mother_low) & ((inside_range / mother_range) <= max_range_ratio)

        prior_was_inside = is_inside.shift(1).fillna(False)
        prior_mother_high = mother_high.shift(1)
        prior_mother_low = mother_low.shift(1)

        raw = pd.Series(np.nan, index=bars.index)
        raw[prior_was_inside & (c > prior_mother_high)] = 1
        raw[prior_was_inside & (c < prior_mother_low)] = -1
        return raw.ffill().fillna(0)


class OpeningRangeBreakout(Strategy):
    """5-minute Opening Range Breakout (ORB), a standard day-trading setup:
    the high/low of the first `range_bars` bars of each session becomes the
    'opening range'; a close beyond that range, confirmed by sitting on the
    same side of the session's cumulative VWAP, triggers an entry that's
    held until the opposite breakout or the session ends (position is reset
    flat at the start of every new session - this is a day-trade setup, not
    a multi-day hold). On daily bars (one bar = one session) this correctly
    never fires - opening range breakout is an inherently intraday concept.

    Session boundary is anchored to 9:30 AM US/Eastern (the NYSE/Nasdaq
    cash-equity open) rather than a raw UTC calendar-day boundary. That
    matters specifically for near-24-hour-traded futures like NQ=F: bars are
    stored as naive UTC timestamps, so a plain midnight-UTC boundary lands
    at ~7-8 PM Eastern - the middle of the overnight Globex session, not the
    market open ORB is actually built around. Bars before 9:30 ET on a given
    date belong to the *prior* session's late trading, not that date's
    opening range.
    Params: range_bars=6 (30 minutes of 5-minute bars).
    """

    PARAM_SPACE = {"range_bars": [3, 6, 9, 12]}

    @property
    def name(self) -> str:
        return f"Opening_Range_Breakout({self.params.get('range_bars', 6)})"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        range_bars = self.params.get("range_bars", 6)
        idx = bars.index
        et = (idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")).tz_convert("America/New_York")
        session_date = et.normalize()
        cash_open = session_date + pd.Timedelta(hours=9, minutes=30)
        dates = session_date.where(et >= cash_open, session_date - pd.Timedelta(days=1))

        orb_high = bars.groupby(dates)["high"].transform(lambda s: s.iloc[:range_bars].max())
        orb_low = bars.groupby(dates)["low"].transform(lambda s: s.iloc[:range_bars].min())

        typical = (bars["high"] + bars["low"] + bars["close"]) / 3
        pv = typical * bars["volume"]
        cum_pv = pv.groupby(dates).cumsum()
        cum_vol = bars["volume"].groupby(dates).cumsum().replace(0, np.nan)
        vwap = cum_pv / cum_vol

        bar_num = bars.groupby(dates).cumcount()
        valid = bar_num >= range_bars
        close = bars["close"]

        raw = pd.Series(np.nan, index=bars.index)
        raw[valid & (close > orb_high) & (close > vwap)] = 1
        raw[valid & (close < orb_low) & (close < vwap)] = -1

        signal = raw.groupby(dates).transform(lambda s: s.ffill()).fillna(0)
        return signal
