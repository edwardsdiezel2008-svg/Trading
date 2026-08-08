"""Classify each bar into a market regime, then attribute a strategy's P&L to
those regimes. This is the "for what reasons" layer: a Sharpe ratio alone
says whether a strategy worked, not why - regime attribution answers that by
showing whether the profit came from trending, ranging, high-volatility, or
low-volatility conditions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import BacktestResult


def _adx(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder's method) - measures trend strength
    regardless of direction. Conventionally: >25 trending, <20 ranging.
    """
    high, low, close = bars["high"], bars["low"], bars["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=bars.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=bars.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def classify_regimes(
    bars: pd.DataFrame,
    adx_period: int = 14,
    trend_threshold: float = 25.0,
    vol_window: int = 50,
) -> pd.DataFrame:
    """Return a DataFrame aligned to `bars` with columns:
      - adx: trend strength
      - trend_regime: 'trending' | 'ranging'
      - realized_vol: rolling std of bar returns
      - vol_regime: 'high_vol' | 'low_vol' (relative to this instrument's own
        trailing median, since "high volatility" is instrument-specific)
      - regime: combined label, e.g. 'trending/high_vol'
    """
    adx = _adx(bars, adx_period)
    trend_regime = pd.Series(np.where(adx >= trend_threshold, "trending", "ranging"), index=bars.index)
    trend_regime[adx.isna()] = np.nan

    returns = bars["close"].pct_change()
    realized_vol = returns.rolling(vol_window).std()
    vol_median = realized_vol.rolling(vol_window * 4, min_periods=vol_window).median()
    vol_regime = pd.Series(np.where(realized_vol >= vol_median, "high_vol", "low_vol"), index=bars.index)
    vol_regime[realized_vol.isna() | vol_median.isna()] = np.nan

    combined = trend_regime.astype(str) + "/" + vol_regime.astype(str)
    combined[trend_regime.isna() | vol_regime.isna()] = np.nan

    return pd.DataFrame({
        "adx": adx,
        "trend_regime": trend_regime,
        "realized_vol": realized_vol,
        "vol_regime": vol_regime,
        "regime": combined,
    })


def attribute_performance(result: BacktestResult, regimes: pd.DataFrame) -> pd.DataFrame:
    """Bucket the strategy's per-bar P&L by regime label and summarize."""
    bar_pnl = result.equity_curve.diff().fillna(0.0)
    df = pd.DataFrame({"pnl": bar_pnl, "position": result.positions}).join(regimes[["regime", "trend_regime", "vol_regime"]])
    df = df.dropna(subset=["regime"])

    grouped = df.groupby("regime").agg(
        total_pnl=("pnl", "sum"),
        mean_pnl_per_bar=("pnl", "mean"),
        bar_count=("pnl", "count"),
        pct_time_in_market=("position", lambda s: (s != 0).mean()),
    )
    grouped["pct_of_bars"] = grouped["bar_count"] / grouped["bar_count"].sum()
    total_abs_pnl = grouped["total_pnl"].abs().sum()
    grouped["pct_of_total_pnl"] = grouped["total_pnl"] / total_abs_pnl if total_abs_pnl else np.nan
    return grouped.sort_values("total_pnl", ascending=False)


def explain_result(result: BacktestResult, regimes: pd.DataFrame) -> str:
    """One-paragraph plain-English summary of which regime(s) drove the
    strategy's profit or loss, for the comparison report.
    """
    attribution = attribute_performance(result, regimes)
    if attribution.empty:
        return f"{result.strategy_name} on {result.instrument}: not enough data to classify regimes."

    best = attribution.iloc[0]
    worst = attribution.iloc[-1]
    total_pnl = attribution["total_pnl"].sum()

    lines = [
        f"{result.strategy_name} on {result.instrument}: net P&L ${total_pnl:,.0f} across {int(attribution['bar_count'].sum())} classified bars.",
        f"  Best regime: '{best.name}' (${best['total_pnl']:,.0f} total, {best['pct_of_bars']:.0%} of time).",
    ]
    if worst.name != best.name:
        lines.append(f"  Worst regime: '{worst.name}' (${worst['total_pnl']:,.0f} total, {worst['pct_of_bars']:.0%} of time).")
    return "\n".join(lines)
