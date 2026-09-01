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


def test_oos_curve_flat_lines_once_a_fold_blows_the_account_negative():
    # A naked short sized at 100% of equity, with no max_loss_fraction floor,
    # can drive the engine's own equity_curve negative (see engine.py's own
    # docstring on this). If a fold boundary lands on that negative point,
    # equity_at_train_end is negative - a truthy value that the old `if
    # equity_at_train_end else 1.0` guard let straight through into a
    # division. That didn't crash (no inf/nan), it silently rescaled the next
    # fold by a *negative* factor instead: a real, discontinuous jump at the
    # fold boundary that kept drifting for the rest of the fold, rather than
    # the flat "no more capital to compound" line the engine's own equity <=
    # 0 convention implies. Assert the actual fixed behavior (flat, no jump)
    # rather than just "no inf/nan", which the bug never produced anyway.
    class AlwaysShort(Strategy):
        PARAM_SPACE = {"k": [1, 2]}

        def generate_signals(self, bars):
            return pd.Series(-1, index=bars.index)

    prices = np.concatenate([np.full(100, 100.0), np.linspace(100, 100_000.0, 100)])
    bars = _bars(prices)
    spec = InstrumentSpec("TEST", "equity", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0)

    wf = run_walk_forward(bars, AlwaysShort, spec, n_folds=3, capital_fraction=1.0, sizing="percent_equity")

    eq = wf.oos_equity_curve
    assert np.isfinite(eq.to_numpy()).all()
    assert len(wf.folds) == 3

    # With this exact setup, fold 2's test window is where the rally drives
    # equity negative, so fold 3 enters with a non-positive equity_at_train_end
    # and must flat-line for its whole test window rather than rescale by a
    # negative factor (which is what the bug did - see comment above).
    fold3 = wf.folds[2]
    assert eq.loc[fold3.test_start] <= 0  # confirms this setup actually exercises the bug's precondition
    seg = eq.loc[fold3.test_start:fold3.test_end]
    assert seg.nunique() == 1, "a fold starting from non-positive equity should flat-line, not rescale"


def test_oos_curve_stays_frozen_even_when_a_later_fold_avoids_the_blowup():
    # A different way for the same "no more capital to compound" invariant to
    # break: unlike the test above (where the SAME strategy behavior blows up
    # equity_at_train_end for both the running total and the fold's own
    # recompute in lockstep), each fold here grid-searches its own best_combo
    # independently. A later fold can pick a combo whose from-bar-0 recompute
    # never touches the earlier blowup at all - so equity_at_train_end comes
    # back positive - even though running_capital (the actual chronological
    # multiplier, built from each fold's OWN realized combo as the walk
    # actually happened) is still negative from an earlier fold's loss. The
    # display must stay frozen on running_capital's sign, not equity_at_train_end's.
    class DirectionPick(Strategy):
        PARAM_SPACE = {"direction": [1, -1]}

        def generate_signals(self, bars):
            return pd.Series(self.params.get("direction", 1), index=bars.index)

    n = 300
    prices = np.empty(n)
    prices[:150] = np.linspace(200.0, 100.0, 150)      # decline: favors short
    prices[150:225] = np.linspace(100.0, 5000.0, 75)   # huge spike: blows up a short
    prices[225:] = np.linspace(5000.0, 5200.0, 75)     # mild continued rise: favors long
    bars = _bars(prices)
    spec = InstrumentSpec("TEST", "equity", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0)

    # max_drawdown_fraction disabled - this test needs the grid search to
    # genuinely pick "short" for a fold that then blows up on the spike (the
    # scenario under test), which the new 5% portfolio-wide drawdown breaker
    # would otherwise short-circuit before the blowup - and would also change
    # which combo the grid search scores as best.
    wf = run_walk_forward(bars, DirectionPick, spec, n_folds=3, capital_fraction=1.0, sizing="percent_equity", max_drawdown_fraction=None)

    assert len(wf.folds) == 3
    # Confirms this setup actually exercises the bug's precondition: fold 2
    # picked "short" (blown up by the spike in its own test window) while
    # fold 3 picked "long" instead.
    assert wf.folds[1].chosen_params["direction"] == -1
    assert wf.folds[2].chosen_params["direction"] == 1

    eq = wf.oos_equity_curve
    fold3 = wf.folds[2]
    assert eq.loc[fold3.test_start] <= 0  # running_capital is still negative entering fold 3
    seg = eq.loc[fold3.test_start:fold3.test_end]
    assert seg.nunique() == 1, "a fold that avoids the blowup must not un-freeze an already-blown account"


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


def test_a_combo_that_raises_during_training_is_skipped_and_never_chosen():
    class PartiallyFlakyStrategy(Strategy):
        PARAM_SPACE = {"level": [90, 100, 999]}

        def generate_signals(self, bars):
            level = self.params.get("level", 100)
            if level == 999:
                raise RuntimeError("this parameter value is intentionally broken")
            return (bars["close"] > level).astype(int)

    bars = _bars(_trending_prices())
    wf = run_walk_forward(bars, PartiallyFlakyStrategy, _spec(), n_folds=4)

    # The broken combo must never win a fold's grid search - it always raises
    # during scoring, so its score is never even considered - and the whole
    # run must still complete rather than crashing on the bad parameter value.
    assert all(f.chosen_params["level"] != 999 for f in wf.folds)
    assert len(wf.folds) == 4
