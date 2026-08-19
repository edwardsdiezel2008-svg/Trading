import sys

import pandas as pd

sys.path.insert(0, ".")

from src.backtest.engine import Trade
from src.backtest.strategies import ALL_STRATEGY_CLASSES
from scripts.build_backtest_lab import (
    MAX_CONFIGS_PER_STRATEGY,
    _bars_json,
    _param_extremes,
    _safe_num,
    _select_chart_ids,
    _thin_grid,
    _trades_json,
    strategy_configs,
)


def test_strategy_configs_covers_at_least_50_real_configurations():
    configs = strategy_configs()
    assert len(configs) >= 50
    # Every strategy class in the library contributes at least its defaults.
    covered = {cls for cls, _ in configs}
    assert covered == set(ALL_STRATEGY_CLASSES)


def test_strategy_configs_params_are_drawn_from_the_strategys_own_param_space():
    for cls, params in strategy_configs():
        for key, value in params.items():
            assert key in cls.PARAM_SPACE, f"{cls.__name__} has no PARAM_SPACE entry for {key!r}"
            assert value in cls.PARAM_SPACE[key], (
                f"{cls.__name__}({key}={value!r}) isn't one of its own documented PARAM_SPACE values"
            )


def test_strategy_configs_runs_the_full_real_grid_per_class_capped_at_50():
    counts = {}
    for cls, _ in strategy_configs():
        counts[cls] = counts.get(cls, 0) + 1
    for cls in ALL_STRATEGY_CLASSES:
        space = cls.PARAM_SPACE
        full_grid_size = 1
        for values in space.values():
            full_grid_size *= len(values)
        expected = min(full_grid_size + 1, MAX_CONFIGS_PER_STRATEGY)  # +1 for hardcoded defaults
        assert counts[cls] == expected, f"{cls.__name__}: expected {expected} configs, got {counts[cls]}"
        assert counts[cls] <= MAX_CONFIGS_PER_STRATEGY


def test_param_extremes_of_a_hypothetically_huge_grid_are_still_just_first_and_last():
    class FakeBig:
        PARAM_SPACE = {"a": list(range(10)), "b": list(range(10))}  # 100 combos

    lo, hi = _param_extremes(FakeBig)
    assert lo == {"a": 0, "b": 0}
    assert hi == {"a": 9, "b": 9}


def test_thin_grid_is_a_no_op_when_the_grid_already_fits_the_budget():
    grid = list(range(10))
    assert _thin_grid(grid, budget=10) is grid
    assert _thin_grid(grid, budget=20) is grid


def test_thin_grid_caps_a_grid_larger_than_the_budget_to_exactly_the_budget():
    # No real strategy's PARAM_SPACE is this large today, so this branch of
    # strategy_configs() is otherwise never exercised - test it directly
    # against a synthetic grid rather than relying on that staying true.
    grid = list(range(1000))
    thinned = _thin_grid(grid, budget=49)
    assert len(thinned) == 49
    assert len(set(thinned)) == 49  # no duplicates
    assert thinned == sorted(thinned)  # order preserved


def test_thin_grid_always_keeps_the_first_and_last_real_value():
    # The strategy's most conservative and most aggressive real combo should
    # survive thinning even when its grid is far bigger than the cap.
    grid = list(range(200))
    thinned = _thin_grid(grid, budget=10)
    assert thinned[0] == grid[0]
    assert thinned[-1] == grid[-1]


def test_safe_num_converts_nan_and_inf_to_none():
    assert _safe_num(float("nan")) is None
    assert _safe_num(float("inf")) is None
    assert _safe_num(float("-inf")) is None
    assert _safe_num(None) is None


def test_safe_num_rounds_a_normal_value():
    assert _safe_num(0.123456, 3) == 0.123


def test_bars_json_shape_is_epoch_seconds_and_close_only():
    idx = pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC")
    bars = pd.DataFrame({
        "open": [1.0, 2.0, 3.0], "high": [1.5, 2.5, 3.5], "low": [0.5, 1.5, 2.5],
        "close": [1.2, 2.2, 3.2], "volume": [10, 20, 30],
    }, index=idx.tz_localize(None))

    out = _bars_json(bars)

    assert len(out) == 3
    assert out[0] == [int(idx[0].timestamp()), 1.2]
    assert out[2] == [int(idx[2].timestamp()), 3.2]


def test_trades_json_maps_entry_and_exit_times_to_integer_bar_positions():
    idx = pd.date_range("2026-01-01", periods=5, freq="5min")
    trade = Trade(
        entry_time=idx[1], exit_time=idx[3], direction=1,
        entry_price=100.0, exit_price=105.0, units=1.0,
        gross_pnl=10.0, costs=1.5, net_pnl=8.5, entry_equity=100000.0,
    )

    out = _trades_json([trade], idx)

    assert out == [[1, 3, 1, 100.0, 105.0, 8.5]]


def _fake_config(total_return, sharpe, is_extreme=False):
    return {"total_return": total_return, "sharpe": sharpe, "_is_extreme": is_extreme}


def test_select_chart_ids_includes_top_n_by_return_and_by_sharpe():
    # Best return, worst sharpe, and vice versa - each should still get in
    # via its own ranking even though it doesn't lead the other one.
    best_return = _fake_config(0.50, 0.1)
    best_sharpe = _fake_config(0.01, 5.0)
    middling = _fake_config(0.10, 1.0)
    computed = [best_return, best_sharpe, middling]

    ids = _select_chart_ids(computed, top_n=1)

    assert id(best_return) in ids
    assert id(best_sharpe) in ids
    assert id(middling) not in ids


def test_select_chart_ids_always_includes_extremes_even_if_low_ranked():
    worst_but_extreme = _fake_config(-0.90, -3.0, is_extreme=True)
    great_but_not_extreme = _fake_config(0.80, 4.0)
    computed = [worst_but_extreme, great_but_not_extreme]

    ids = _select_chart_ids(computed, top_n=1)

    assert id(worst_but_extreme) in ids  # extreme, so charted regardless of rank
    assert id(great_but_not_extreme) in ids  # also charted, tops both rankings


def test_select_chart_ids_excludes_none_metrics_from_ranking_not_from_extremes():
    none_metrics_extreme = _fake_config(None, None, is_extreme=True)
    none_metrics_ordinary = _fake_config(None, None, is_extreme=False)
    ranked = _fake_config(0.05, 0.5)
    computed = [none_metrics_extreme, none_metrics_ordinary, ranked]

    ids = _select_chart_ids(computed, top_n=5)

    assert id(none_metrics_extreme) in ids  # kept via _is_extreme despite None metrics
    assert id(none_metrics_ordinary) not in ids  # no metrics to rank by, not extreme
    assert id(ranked) in ids
