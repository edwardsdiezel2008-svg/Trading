"""Regime-conditional meta-strategy selector: learns which of several
strategies to trust given the CURRENT market regime, rather than picking one
strategy and running it unconditionally for the whole backtest period.

Built directly on top of regime.py's classify_regimes()/attribute_performance()
- no new regime detection, just a decision layer on top of it - and validated
with the same walk-forward discipline as walkforward.py: the regime ->
strategy mapping is only ever learned on a TRAIN window and then applied,
unmodified, to the following unseen TEST window. That's the one thing that
keeps this from being just another way to curve-fit: a meta-model that
"learns" from the same data it's graded on isn't learning anything, it's
memorizing.

Known limitation, stated up front rather than glossed over: this operates on
a genuinely small dataset by ML standards (a few thousand bars, a handful of
regime buckets, a handful of assets). A regime bucket needs at least
`min_regime_bars` bars of TRAIN history and a net-profitable historical edge
before it's assigned a strategy at all - anything thinner defaults to flat
rather than picking on a coin-flip's worth of evidence - but that guard
reduces overfitting risk, it doesn't eliminate it. Treat the out-of-sample
numbers here with the same skepticism as any other walk-forward result, not
more.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .engine import BacktestResult, run_backtest
from .instruments import InstrumentSpec
from .metrics import compute_metrics
from .regime import attribute_performance, classify_regimes
from .strategies.base import Strategy


class _PrecomputedSignalStrategy(Strategy):
    """Internal adapter: wraps an already-computed target-position Series so
    it can be replayed through the same run_backtest() execution/cost/
    liquidation logic every other strategy uses, instead of duplicating that
    logic here. Not a real strategy - never added to ALL_STRATEGY_CLASSES,
    never shown on the dashboard as a strategy name in its own right.
    """

    @property
    def name(self) -> str:
        return "MetaStrategySelector"

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        signal = self.params["signal"]
        return signal.reindex(bars.index).fillna(0)


def select_strategy_per_regime(
    bars: pd.DataFrame,
    strategy_instances: list[Strategy],
    spec: InstrumentSpec,
    min_regime_bars: int = 20,
    **engine_kwargs,
) -> dict[str, str]:
    """For each regime label seen in `bars`, find which strategy had the best
    mean P&L per bar *while that regime was in effect*. A regime only gets an
    assignment if (a) it had at least `min_regime_bars` bars of history to
    judge from, and (b) the best strategy found was actually net profitable
    in that regime - "least bad of a bad bunch" isn't a real edge, so those
    regimes are left unassigned (the meta-selector goes flat instead).
    """
    regimes = classify_regimes(bars)
    per_regime_scores: dict[str, dict[str, float]] = {}

    for strat in strategy_instances:
        try:
            result = run_backtest(bars, strat, spec, **engine_kwargs)
        except Exception:
            continue
        attribution = attribute_performance(result, regimes)
        for regime_label, row in attribution.iterrows():
            if row["bar_count"] < min_regime_bars:
                continue
            per_regime_scores.setdefault(regime_label, {})[strat.name] = row["mean_pnl_per_bar"]

    selection = {}
    for regime_label, scores in per_regime_scores.items():
        best_strategy = max(scores, key=scores.get)
        if scores[best_strategy] > 0:
            selection[regime_label] = best_strategy
    return selection


@dataclass
class MetaFold:
    fold_idx: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    regime_map: dict
    test_metrics: dict


@dataclass
class MetaStrategyResult:
    instrument: str
    folds: list = field(default_factory=list)
    oos_equity_curve: pd.Series = None
    oos_metrics: dict = None
    live_regime_map: dict = None


def run_meta_strategy_walkforward(
    bars: pd.DataFrame,
    strategy_classes: list,
    spec: InstrumentSpec,
    n_folds: int = 5,
    min_regime_bars: int = 20,
    initial_capital: float = 100_000.0,
    freq_hint: str | None = None,
    **engine_kwargs,
) -> MetaStrategyResult:
    n = len(bars)
    edges = np.linspace(0, n, n_folds + 2).astype(int)
    if edges[1] < 30:
        raise ValueError(
            f"First training chunk is only {edges[1]} bars - too little to warm up indicators reliably. "
            f"Use more data or fewer folds (n_folds={n_folds})."
        )

    running_capital = initial_capital
    folds: list[MetaFold] = []
    equity_pieces = []
    combined_trades = []

    for k in range(1, n_folds + 1):
        train_end, test_end = int(edges[k]), int(edges[k + 1])
        if test_end <= train_end:
            continue

        train_bars = bars.iloc[:train_end]
        train_instances = [cls() for cls in strategy_classes]
        regime_map = select_strategy_per_regime(train_bars, train_instances, spec, min_regime_bars, **engine_kwargs)

        # Regimes and each strategy's own signal both get computed over full
        # history through test_end (real warmup) and then sliced to the test
        # window only - the same no-lookahead pattern run_walk_forward uses.
        history_bars = bars.iloc[:test_end]
        test_regimes = classify_regimes(history_bars)["regime"].iloc[train_end:test_end]

        signals_by_name = {}
        for cls in strategy_classes:
            strat = cls()
            try:
                signals_by_name[strat.name] = strat.generate_signals(history_bars).iloc[train_end:test_end]
            except Exception:
                continue

        test_bars = bars.iloc[train_end:test_end]
        meta_signal = pd.Series(0.0, index=test_bars.index)
        for regime_label, strat_name in regime_map.items():
            sig = signals_by_name.get(strat_name)
            if sig is None:
                continue
            mask = test_regimes == regime_label
            meta_signal[mask] = sig[mask]

        meta_strat = _PrecomputedSignalStrategy(params={"signal": meta_signal})
        fold_result = run_backtest(test_bars, meta_strat, spec, initial_capital=100_000.0, **engine_kwargs)
        fold_metrics = compute_metrics(fold_result, initial_capital=100_000.0, freq_hint=freq_hint)

        multiple = (fold_result.equity_curve.iloc[-1] / 100_000.0) if len(fold_result.equity_curve) else 1.0
        rebased = (fold_result.equity_curve / 100_000.0) * running_capital
        equity_pieces.append(rebased)
        combined_trades.extend(fold_result.trades)
        running_capital = running_capital * multiple

        folds.append(MetaFold(
            fold_idx=k,
            train_start=bars.index[0], train_end=bars.index[train_end - 1],
            test_start=bars.index[train_end], test_end=bars.index[test_end - 1],
            regime_map=regime_map,
            test_metrics=fold_metrics,
        ))

    if not folds:
        raise ValueError("No folds could be evaluated - increase the dataset size or lower n_folds.")

    oos_equity = pd.concat(equity_pieces)
    oos_result = BacktestResult(
        strategy_name="MetaStrategySelector", instrument=spec.symbol,
        bars=bars.iloc[int(edges[1]):int(edges[n_folds + 1])],
        signals=pd.Series(dtype=float), positions=pd.Series(dtype=float),
        equity_curve=oos_equity, trades=combined_trades,
    )
    oos_metrics = compute_metrics(oos_result, initial_capital=initial_capital, freq_hint=freq_hint)

    live_regime_map = select_strategy_per_regime(
        bars, [cls() for cls in strategy_classes], spec, min_regime_bars, **engine_kwargs
    )

    return MetaStrategyResult(
        instrument=spec.symbol, folds=folds,
        oos_equity_curve=oos_equity, oos_metrics=oos_metrics,
        live_regime_map=live_regime_map,
    )
