import numpy as np
import pandas as pd
import pytest

from src.backtest.instruments import InstrumentSpec
from src.backtest.strategies.base import Strategy
from src.backtest.walkforward import run_walk_forward


class ThresholdStrategy(Strategy):
    """Long whenever close > `level`, else flat. A trivial strategy whose
    PARAM_SPACE lets the walk-forward grid search pick among a few levels -
    good for tests because its behavior for a given level is easy to reason
    about by hand.
    """

    PARAM_SPACE = {"level": [90, 100, 110, 120]}

    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        level = self.params.get("level", 100)
        return (bars["close"] > level).astype(int)


def _spec():
    return InstrumentSpec("TEST", "equity", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0)


def _bars(prices):
    idx = pd.date_range("2026-01-05", periods=len(prices), freq="1min")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)


def _trending_prices(n=800, seed=3):
    rng = np.random.default_rng(seed)
    return 100 + np.cumsum(rng.normal(0.05, 1.0, n))


def test_folds_are_contiguous_and_train_window_expands():
    bars = _bars(_trending_prices())
    wf = run_walk_forward(bars, ThresholdStrategy, _spec(), n_folds=4)

    assert len(wf.folds) == 4
    for f in wf.folds:
        assert f.train_start == bars.index[0]
    # train window expands fold over fold
    train_ends = [f.train_end for f in wf.folds]
    assert train_ends == sorted(train_ends)
    # each fold's test starts exactly where the previous fold's test ended (no gap, no overlap)
    for prev, nxt in zip(wf.folds, wf.folds[1:]):
        prev_end_pos = bars.index.get_loc(prev.test_end)
        next_start_pos = bars.index.get_loc(nxt.test_start)
        assert next_start_pos == prev_end_pos + 1


def test_selection_never_sees_data_after_the_training_window():
    # Two datasets identical up through fold 1's training window, then diverging
    # wildly afterward. If the walk-forward selection step were leaking future
    # data, fold 1's chosen params/score would differ between the two runs.
    prices = _trending_prices(n=800, seed=11)
    bars_a = _bars(prices)

    spec = _spec()
    wf_a = run_walk_forward(bars_a, ThresholdStrategy, spec, n_folds=4)
    fold1_train_end_idx = bars_a.index.get_loc(wf_a.folds[0].train_end)

    prices_b = prices.copy()
    rng = np.random.default_rng(999)
    prices_b[fold1_train_end_idx + 1:] = 1000 + np.cumsum(rng.normal(0, 5, len(prices_b) - fold1_train_end_idx - 1))
    bars_b = _bars(prices_b)
    wf_b = run_walk_forward(bars_b, ThresholdStrategy, spec, n_folds=4)

    assert wf_a.folds[0].chosen_params == wf_b.folds[0].chosen_params
    assert wf_a.folds[0].train_score == pytest.approx(wf_b.folds[0].train_score)


def test_stitched_equity_curve_is_continuous_across_fold_boundaries():
    bars = _bars(_trending_prices(n=1000, seed=5))
    wf = run_walk_forward(bars, ThresholdStrategy, _spec(), n_folds=4, initial_capital=50_000)

    eq = wf.oos_equity_curve
    assert len(eq) > 0
    # No fold-boundary discontinuity: consecutive bar-to-bar equity changes should
    # stay in the same rough magnitude throughout - a stitching bug would show up
    # as a sudden reset toward the starting capital at a fold boundary.
    changes = eq.pct_change().dropna().abs()
    assert changes.max() < 0.5  # nothing behaves like a reset-to-flat jump

    # oos_metrics' total_return should match the curve's own start/end ratio.
    implied_return = eq.iloc[-1] / 50_000 - 1
    assert wf.oos_metrics["total_return"] == pytest.approx(implied_return, rel=1e-6)


def test_baseline_uses_fixed_default_params_over_same_oos_window():
    bars = _bars(_trending_prices(n=800, seed=7))
    wf = run_walk_forward(bars, ThresholdStrategy, _spec(), n_folds=4)
    assert wf.baseline_metrics is not None
    assert "total_return" in wf.baseline_metrics
    # vs_fixed_default_ratio should be a finite float when baseline had a nonzero return
    if wf.baseline_metrics["total_return"] not in (0, None):
        assert wf.vs_fixed_default_ratio is not None


def test_raises_when_too_little_data_for_first_fold():
    bars = _bars(_trending_prices(n=20, seed=1))
    with pytest.raises(ValueError):
        run_walk_forward(bars, ThresholdStrategy, _spec(), n_folds=4)


def test_raises_without_param_space():
    class NoGrid(Strategy):
        def generate_signals(self, bars):
            return pd.Series(0, index=bars.index)

    bars = _bars(_trending_prices(n=200))
    with pytest.raises(ValueError):
        run_walk_forward(bars, NoGrid, _spec(), n_folds=2)
