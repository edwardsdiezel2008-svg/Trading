"""Performance statistics computed from a BacktestResult."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import BacktestResult

_BARS_PER_YEAR = {
    "1min": 252 * 390,
    "5min": 252 * 78,
    "15min": 252 * 26,
    "30min": 252 * 13,
    "1h": 252 * 7,
    "1D": 252,
    "1W": 52,
}


def _annualization_factor(bars: pd.DataFrame, freq_hint: str | None) -> float:
    if freq_hint and freq_hint in _BARS_PER_YEAR:
        return _BARS_PER_YEAR[freq_hint]
    if len(bars.index) < 2:
        return 252.0
    median_delta = pd.Series(bars.index).diff().dropna().median()
    seconds = median_delta.total_seconds()
    if seconds <= 0:
        return 252.0
    trading_seconds_per_year = 252 * 6.5 * 3600  # regular session approximation
    return trading_seconds_per_year / seconds


def compute_metrics(result: BacktestResult, initial_capital: float, freq_hint: str | None = None) -> dict:
    equity = result.equity_curve
    returns = equity.pct_change().dropna()
    ann_factor = _annualization_factor(result.bars, freq_hint)

    # initial_capital can be non-positive here (walk-forward passes a fold's
    # own equity_at_train_end, which is <= 0 once that fold started already
    # blown) - dividing by it would flip signs into a misleading ratio rather
    # than error, so treat it the same "flat, no return to report" way the
    # rest of walkforward.py treats an already-blown account.
    total_return = (equity.iloc[-1] / initial_capital) - 1 if len(equity) and initial_capital > 0 else 0.0
    n_periods = len(equity)
    years = n_periods / ann_factor if ann_factor else np.nan
    # Annualizing a short backtest compounds noise into meaningless numbers
    # (a few days of decent returns can "annualize" to absurd figures), so
    # CAGR/Calmar are only reported once the backtest spans at least a month.
    # total_return is always exact regardless of span - use that for short runs.
    min_years_for_annualization = 1 / 12
    can_annualize = years and years >= min_years_for_annualization and equity.iloc[-1] > 0 and initial_capital > 0
    cagr = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1 if can_annualize else np.nan

    vol = returns.std()
    mean_ret = returns.mean()
    sharpe = (mean_ret / vol) * np.sqrt(ann_factor) if vol and vol > 0 else np.nan

    downside = returns[returns < 0]
    downside_std = downside.std()
    sortino = (mean_ret / downside_std) * np.sqrt(ann_factor) if downside_std and downside_std > 0 else np.nan

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = drawdown.min() if len(drawdown) else np.nan

    calmar = cagr / abs(max_drawdown) if max_drawdown and max_drawdown < 0 and not np.isnan(cagr) else np.nan

    trades = result.trades
    n_trades = len(trades)
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    win_rate = len(wins) / n_trades if n_trades else np.nan
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = -sum(t.net_pnl for t in losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (np.inf if gross_profit > 0 else np.nan)
    avg_win = np.mean([t.net_pnl for t in wins]) if wins else np.nan
    avg_loss = np.mean([t.net_pnl for t in losses]) if losses else np.nan
    avg_trade = np.mean([t.net_pnl for t in trades]) if trades else np.nan
    avg_bars_held = np.mean([t.bars_held for t in trades]) if trades else np.nan
    total_costs = sum(t.costs for t in trades)

    exposure = (result.positions != 0).mean() if len(result.positions) else np.nan

    return {
        "strategy": result.strategy_name,
        "instrument": result.instrument,
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "num_trades": n_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_trade": avg_trade,
        "avg_bars_held": avg_bars_held,
        "total_costs": total_costs,
        "exposure": exposure,
        "final_equity": equity.iloc[-1] if len(equity) else initial_capital,
    }


def metrics_table(results_with_capital: list[tuple[BacktestResult, float]], freq_hint: str | None = None) -> pd.DataFrame:
    rows = [compute_metrics(result, capital, freq_hint) for result, capital in results_with_capital]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
    return df
