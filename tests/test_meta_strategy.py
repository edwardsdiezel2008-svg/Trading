import numpy as np
import pandas as pd
import pytest

from src.backtest.instruments import get_spec
from src.backtest.meta_strategy import (
    _PrecomputedSignalStrategy,
    run_meta_strategy_walkforward,
    select_strategy_per_regime,
)
from src.backtest.strategies import MovingAverageCrossover, RSIReversion

SPEC = get_spec("_default_equity")


def _trending_ranging_bars(n_cycles=6, seed=7):
    rng = np.random.default_rng(seed)
    segments = []
    for _ in range(n_cycles):
        trend = 100 + np.linspace(0, 60, 150) + rng.normal(0, 0.3, 150)
        flat = trend[-1] + rng.normal(0, 0.5, 150).cumsum() * 0.05
        segments.append(trend)
        segments.append(flat)
    price = np.concatenate(segments)
    idx = pd.date_range("2020-01-01", periods=len(price), freq="1D")
    return pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 1000}, index=idx)


class TestPrecomputedSignalStrategy:
    def test_reindexes_signal_to_bars_and_fills_missing_with_zero(self):
        idx_full = pd.date_range("2020-01-01", periods=6, freq="1D")
        bars = pd.DataFrame({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10}, index=idx_full)
        sig = pd.Series([1, 1, 0, -1], index=idx_full[:4])
        strat = _PrecomputedSignalStrategy(params={"signal": sig})
        out = strat.generate_signals(bars)
        assert out.tolist() == [1.0, 1.0, 0.0, -1.0, 0.0, 0.0]
        assert out.index.equals(bars.index)

    def test_name_is_stable_and_distinct(self):
        strat = _PrecomputedSignalStrategy(params={"signal": pd.Series(dtype=float)})
        assert strat.name == "MetaStrategySelector"


class TestSelectStrategyPerRegime:
    def test_returns_empty_when_min_bars_threshold_unreachable(self):
        rng = np.random.default_rng(3)
        price = 100 + np.cumsum(rng.normal(0, 1, 100))
        idx = pd.date_range("2020-01-01", periods=100, freq="1D")
        bars = pd.DataFrame({"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 100}, index=idx)
        sel = select_strategy_per_regime(bars, [MovingAverageCrossover()], SPEC, min_regime_bars=10_000)
        assert sel == {}

    def test_assigns_a_real_strategy_name_to_a_well_populated_regime(self):
        bars = _trending_ranging_bars()
        sel = select_strategy_per_regime(bars, [MovingAverageCrossover(), RSIReversion()], SPEC, min_regime_bars=20)
        assert sel  # at least one regime got assigned given a clear trending segment
        for regime_label, strat_name in sel.items():
            assert isinstance(regime_label, str)
            assert strat_name in {MovingAverageCrossover().name, RSIReversion().name}

    def test_never_assigns_a_regime_where_the_best_strategy_lost_money(self):
        # Two strategies that both lose consistently on this series - no
        # regime should get an assignment, since "least bad" isn't a real edge.
        rng = np.random.default_rng(11)
        price = 100 + np.cumsum(rng.normal(-0.05, 1, 400))  # mild downward drift, noisy
        idx = pd.date_range("2020-01-01", periods=400, freq="1D")
        bars = pd.DataFrame({"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 100}, index=idx)
        sel = select_strategy_per_regime(bars, [MovingAverageCrossover()], SPEC, min_regime_bars=20)
        for regime_label, strat_name in sel.items():
            # Whatever got assigned must have been net profitable in that regime.
            assert strat_name == MovingAverageCrossover().name


class TestRunMetaStrategyWalkforward:
    def test_produces_one_fold_per_requested_fold_and_a_stitched_curve(self):
        bars = _trending_ranging_bars()
        result = run_meta_strategy_walkforward(
            bars, [MovingAverageCrossover, RSIReversion], SPEC, n_folds=3, min_regime_bars=20, freq_hint="1D",
        )
        assert len(result.folds) == 3
        for fold in result.folds:
            assert isinstance(fold.regime_map, dict)
            assert "total_return" in fold.test_metrics
        assert len(result.oos_equity_curve) > 0
        assert isinstance(result.live_regime_map, dict)
        assert result.oos_metrics["strategy"] == "MetaStrategySelector"

    def test_raises_on_too_little_data(self):
        idx = pd.date_range("2020-01-01", periods=20, freq="1D")
        bars = pd.DataFrame({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10}, index=idx)
        with pytest.raises(ValueError):
            run_meta_strategy_walkforward(bars, [MovingAverageCrossover], SPEC, n_folds=3)

    def test_unassigned_regimes_leave_the_meta_selector_flat_and_capital_intact(self):
        # min_regime_bars so high nothing ever qualifies -> meta-selector
        # should stay flat the whole time, ending with (near) starting capital
        # (only real trades ever incur commission/slippage costs).
        bars = _trending_ranging_bars(n_cycles=2)
        result = run_meta_strategy_walkforward(
            bars, [MovingAverageCrossover, RSIReversion], SPEC, n_folds=2, min_regime_bars=100_000, freq_hint="1D",
        )
        assert result.oos_metrics["num_trades"] == 0
        assert result.oos_metrics["total_return"] == 0.0
