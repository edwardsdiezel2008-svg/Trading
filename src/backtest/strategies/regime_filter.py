"""Wraps another strategy and flattens its signals during specific regimes,
based on what regime attribution actually showed for that strategy - not a
blind "only trade when trending" rule, but a targeted exclusion of whichever
regime bucket(s) were genuinely losers.

This is the legitimate version of "improve the backtest": the filter is
motivated by an explanation (attribute_performance() showed this regime lost
money for this specific strategy), not by searching parameter space until a
number looks good. It can still make things worse - cutting a regime removes
both its losses AND any winning trades that happened to fall in it - so
always compare filtered vs. unfiltered before trusting it.
"""
from __future__ import annotations

import pandas as pd

from ..regime import classify_regimes
from .base import Strategy


class RegimeFilteredStrategy(Strategy):
    def __init__(
        self,
        base_strategy: Strategy,
        excluded_regimes: set[str] | None = None,
        allowed_regimes: set[str] | None = None,
        adx_period: int = 14,
        trend_threshold: float = 25.0,
        vol_window: int = 50,
    ):
        """Regime labels are the combined form from regime.classify_regimes:
        'trending/low_vol', 'trending/high_vol', 'ranging/low_vol', 'ranging/high_vol'.
        Pass exactly one of excluded_regimes (blacklist - trade everywhere except
        these) or allowed_regimes (whitelist - trade only in these).
        """
        if bool(excluded_regimes) == bool(allowed_regimes):
            raise ValueError("Pass exactly one of excluded_regimes or allowed_regimes.")
        super().__init__(params={})
        self.base_strategy = base_strategy
        self.excluded_regimes = set(excluded_regimes) if excluded_regimes else None
        self.allowed_regimes = set(allowed_regimes) if allowed_regimes else None
        self.adx_period = adx_period
        self.trend_threshold = trend_threshold
        self.vol_window = vol_window

    @property
    def name(self) -> str:
        if self.excluded_regimes:
            desc = "not " + "|".join(sorted(self.excluded_regimes))
        else:
            desc = "only " + "|".join(sorted(self.allowed_regimes))
        return f"{self.base_strategy.name} [{desc}]"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        raw = self.base_strategy.generate_signals(bars)
        regimes = classify_regimes(
            bars, adx_period=self.adx_period, trend_threshold=self.trend_threshold, vol_window=self.vol_window
        )
        regime_label = regimes["regime"]

        if self.excluded_regimes:
            blocked = regime_label.isin(self.excluded_regimes)
        else:
            # Unclassified (warmup) bars aren't in allowed_regimes either -> blocked (flat).
            blocked = ~regime_label.isin(self.allowed_regimes)

        return raw.where(~blocked, 0)
