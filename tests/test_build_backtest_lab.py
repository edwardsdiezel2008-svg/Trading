import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, ".")

from src.backtest.engine import Trade
from src.backtest.strategies import ALL_STRATEGY_CLASSES
from scripts.build_backtest_lab import _bars_json, _safe_num, _trades_json, strategy_configs


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


def test_strategy_configs_gives_each_class_the_default_plus_up_to_two_extremes():
    counts = {}
    for cls, _ in strategy_configs():
        counts[cls] = counts.get(cls, 0) + 1
    for cls in ALL_STRATEGY_CLASSES:
        assert 1 <= counts[cls] <= 3


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
