"""Walk-forward validation: the one thing an in-sample backtest can't tell you.

Every metric produced by `report.py` is in-sample - the strategy (and its
parameters) are evaluated on the same data used to pick them, which is
exactly the setup that makes overfitting look like alpha. Walk-forward
validation fixes that by never letting a parameter choice see the data it's
graded on:

  1. Split the bars into `n_folds + 1` contiguous chronological chunks.
  2. For fold k, grid-search PARAM_SPACE on chunk[0:k] ("train") only.
  3. Apply the winning parameters to chunk[k] ("test") - data the selection
     step never touched - and record how it did.
  4. Roll forward (the train window expands each fold) and repeat.
  5. Stitch the test-fold results into one continuous out-of-sample equity
     curve; that curve, not the in-sample number, is the honest estimate of
     what this strategy would have done.

Indicators still get a proper warmup: each fold's backtest actually runs
over bars[0:test_end], so moving averages etc. see real history through the
train period. Only the equity/trades from the test slice are reported and
stitched - the selection step never used the test slice's data, so this
isn't lookahead, it's just avoiding an artificial cold-start.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .engine import BacktestResult, run_backtest
from .instruments import InstrumentSpec
from .metrics import compute_metrics


@dataclass
class Fold:
    fold_idx: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    chosen_params: dict
    train_score: float
    test_metrics: dict


@dataclass
class WalkForwardResult:
    strategy_name: str
    instrument: str
    folds: list = field(default_factory=list)
    oos_equity_curve: pd.Series = None
    oos_metrics: dict = None
    baseline_metrics: dict = None
    vs_fixed_default_ratio: float = None


def _param_combinations(param_space: dict) -> list[dict]:
    keys = list(param_space.keys())
    values = [param_space[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def _score(metrics: dict, selection_metric: str) -> float:
    v = metrics.get(selection_metric)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return -np.inf
    return v


def run_walk_forward(
    bars: pd.DataFrame,
    strategy_cls,
    spec: InstrumentSpec,
    n_folds: int = 5,
    selection_metric: str = "sharpe",
    initial_capital: float = 100_000.0,
    freq_hint: str | None = None,
    **engine_kwargs,
) -> WalkForwardResult:
    param_space = getattr(strategy_cls, "PARAM_SPACE", None)
    if not param_space:
        raise ValueError(f"{strategy_cls.__name__} has no PARAM_SPACE defined for walk-forward optimization.")
    combos = _param_combinations(param_space)

    n = len(bars)
    edges = np.linspace(0, n, n_folds + 2).astype(int)
    if edges[1] < 30:
        raise ValueError(
            f"First training chunk is only {edges[1]} bars - too little to warm up indicators reliably. "
            f"Use more data or fewer folds (n_folds={n_folds})."
        )

    running_capital = initial_capital
    folds: list[Fold] = []
    equity_pieces, bars_pieces, positions_pieces, signals_pieces = [], [], [], []
    combined_trades = []

    for k in range(1, n_folds + 1):
        train_end, test_end = int(edges[k]), int(edges[k + 1])
        if test_end <= train_end:
            continue

        train_bars = bars.iloc[:train_end]
        best_combo, best_score = combos[0], -np.inf
        for combo in combos:
            strat = strategy_cls(params=combo)
            try:
                res = run_backtest(train_bars, strat, spec, initial_capital=100_000.0, **engine_kwargs)
            except Exception:
                continue
            score = _score(compute_metrics(res, 100_000.0, freq_hint=freq_hint), selection_metric)
            if score > best_score:
                best_score, best_combo = score, combo

        full_res = run_backtest(bars.iloc[:test_end], strategy_cls(params=best_combo), spec, initial_capital=100_000.0, **engine_kwargs)
        eq = full_res.equity_curve
        equity_at_train_end = eq.iloc[train_end - 1]
        # Non-positive (not just exactly zero) equity means the account is already
        # blown - the same convention _position_size() uses to stop opening new
        # positions. Dividing by a negative base would still "succeed" numerically
        # but flip signs into a misleading ratio, so both this and rebased below
        # treat the fold as flat (no more compounding possible) once equity <= 0.
        multiple = (eq.iloc[-1] / equity_at_train_end) if equity_at_train_end > 0 else 1.0

        test_bars = bars.iloc[train_end:test_end]
        test_equity_abs = eq.iloc[train_end:test_end]
        test_positions = full_res.positions.iloc[train_end:test_end]
        test_signals = full_res.signals.iloc[train_end:test_end]
        test_start_time, test_end_time = bars.index[train_end], bars.index[test_end - 1]
        fold_trades = [t for t in full_res.trades if test_start_time <= t.exit_time <= test_end_time]

        fold_result = BacktestResult(
            strategy_name=strategy_cls.__name__, instrument=spec.symbol, bars=test_bars,
            signals=test_signals, positions=test_positions, equity_curve=test_equity_abs, trades=fold_trades,
        )
        fold_metrics = compute_metrics(fold_result, initial_capital=equity_at_train_end, freq_hint=freq_hint)

        # Anchor to equity_at_train_end (not test_equity_abs.iloc[0]) so this piece's
        # first value already reflects the first test bar's P&L, matching `multiple`
        # below - otherwise the stitched curve would silently reset to flat at every
        # fold boundary instead of compounding continuously through it.
        if equity_at_train_end > 0:
            rebased = (test_equity_abs / equity_at_train_end) * running_capital
        else:
            rebased = pd.Series(running_capital, index=test_equity_abs.index)
        equity_pieces.append(rebased)
        bars_pieces.append(test_bars)
        positions_pieces.append(test_positions)
        signals_pieces.append(test_signals)
        combined_trades.extend(fold_trades)
        running_capital = running_capital * multiple

        folds.append(Fold(
            fold_idx=k,
            train_start=bars.index[0], train_end=bars.index[train_end - 1],
            test_start=test_start_time, test_end=test_end_time,
            chosen_params=best_combo,
            train_score=None if best_score == -np.inf else best_score,
            test_metrics=fold_metrics,
        ))

    if not folds:
        raise ValueError("No folds could be evaluated - increase the dataset size or lower n_folds.")

    oos_equity = pd.concat(equity_pieces)
    oos_result = BacktestResult(
        strategy_name=f"{strategy_cls.__name__} (walk-forward)", instrument=spec.symbol,
        bars=pd.concat(bars_pieces), signals=pd.concat(signals_pieces),
        positions=pd.concat(positions_pieces), equity_curve=oos_equity, trades=combined_trades,
    )
    oos_metrics = compute_metrics(oos_result, initial_capital=initial_capital, freq_hint=freq_hint)

    # Fixed-default baseline over the exact same out-of-sample window, for an
    # apples-to-apples answer to "was re-optimizing each fold even worth it?"
    oos_start_idx, oos_end_idx = int(edges[1]), int(edges[n_folds + 1])
    baseline_full = run_backtest(bars.iloc[:oos_end_idx], strategy_cls(), spec, initial_capital=100_000.0, **engine_kwargs)
    baseline_entry_equity = baseline_full.equity_curve.iloc[oos_start_idx - 1]
    oos_start_time, oos_end_time = bars.index[oos_start_idx], bars.index[oos_end_idx - 1]
    baseline_result = BacktestResult(
        strategy_name=f"{strategy_cls.__name__} (fixed default)", instrument=spec.symbol,
        bars=bars.iloc[oos_start_idx:oos_end_idx], signals=baseline_full.signals.iloc[oos_start_idx:oos_end_idx],
        positions=baseline_full.positions.iloc[oos_start_idx:oos_end_idx],
        equity_curve=baseline_full.equity_curve.iloc[oos_start_idx:oos_end_idx],
        trades=[t for t in baseline_full.trades if oos_start_time <= t.exit_time <= oos_end_time],
    )
    baseline_metrics = compute_metrics(baseline_result, initial_capital=baseline_entry_equity, freq_hint=freq_hint)

    base_ret = baseline_metrics.get("total_return")
    oos_ret = oos_metrics.get("total_return")
    ratio = (oos_ret / base_ret) if base_ret not in (None, 0) and not np.isnan(base_ret) else None

    return WalkForwardResult(
        strategy_name=strategy_cls.__name__, instrument=spec.symbol, folds=folds,
        oos_equity_curve=oos_equity, oos_metrics=oos_metrics,
        baseline_metrics=baseline_metrics, vs_fixed_default_ratio=ratio,
    )
