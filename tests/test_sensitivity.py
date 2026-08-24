import numpy as np
import pandas as pd
import pytest

from src.backtest.instruments import InstrumentSpec
from src.backtest.sensitivity import param_sensitivity
from src.backtest.strategies import MovingAverageCrossover
from src.backtest.strategies.base import Strategy


def _spec():
    return InstrumentSpec("TEST", "equity", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0)


def _bars(n=600, seed=2):
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0.02, 1.0, n))
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    return pd.DataFrame({"open": price, "high": price + 0.3, "low": price - 0.3, "close": price, "volume": 100}, index=idx)


def test_sweeps_every_value_in_param_space():
    bars = _bars()
    result = param_sensitivity(bars, MovingAverageCrossover, _spec())

    space = MovingAverageCrossover.PARAM_SPACE
    for pname, values in space.items():
        swept = sorted(result.detail[result.detail["parameter"] == pname]["value"].tolist())
        assert swept == sorted(values)


def test_summary_has_one_row_per_parameter_with_correct_counts():
    bars = _bars()
    result = param_sensitivity(bars, MovingAverageCrossover, _spec())
    space = MovingAverageCrossover.PARAM_SPACE

    assert set(result.summary.index) == set(space.keys())
    for pname, values in space.items():
        assert result.summary.loc[pname, "n_values"] == len(values)


def test_base_params_hold_other_parameters_fixed():
    bars = _bars()
    # Sweep only 'fast'; 'slow' should stay pinned at the base_params value for
    # every row in that sweep (proving the sweep isn't accidentally varying
    # every parameter at once).
    result = param_sensitivity(bars, MovingAverageCrossover, _spec(), base_params={"slow": 40})
    fast_rows = result.detail[result.detail["parameter"] == "fast"]
    assert len(fast_rows) == len(MovingAverageCrossover.PARAM_SPACE["fast"])
    # re-run each combo manually to confirm slow=40 was actually used
    from src.backtest.engine import run_backtest
    from src.backtest.metrics import compute_metrics
    for _, row in fast_rows.iterrows():
        strat = MovingAverageCrossover(params={"fast": row["value"], "slow": 40})
        res = run_backtest(bars, strat, _spec(), initial_capital=100_000.0)
        m = compute_metrics(res, 100_000.0)
        assert m["total_return"] == pytest.approx(row["total_return"])


def test_raises_without_param_space():
    class NoGrid(Strategy):
        def generate_signals(self, bars):
            return pd.Series(0, index=bars.index)

    with pytest.raises(ValueError):
        param_sensitivity(_bars(), NoGrid, _spec())


def test_a_parameter_value_that_raises_gets_nan_metrics_instead_of_crashing_the_sweep():
    class FlakyStrategy(Strategy):
        PARAM_SPACE = {"level": [1, 2, 3]}

        def generate_signals(self, bars):
            if self.params.get("level") == 2:
                raise ValueError("this parameter value blows up")
            return pd.Series(0, index=bars.index)

    result = param_sensitivity(_bars(), FlakyStrategy, _spec())

    good_rows = result.detail[result.detail["value"] != 2]
    bad_row = result.detail[result.detail["value"] == 2].iloc[0]

    assert (good_rows["num_trades"] == 0).all()  # AlwaysFlat-style: no trades, but a real result
    assert np.isnan(bad_row["total_return"])
    assert np.isnan(bad_row["sharpe"])
    assert np.isnan(bad_row["max_drawdown"])
    assert bad_row["num_trades"] == 0
