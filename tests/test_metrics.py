import numpy as np
import pandas as pd

from src.backtest.engine import Trade, BacktestResult
from src.backtest.metrics import compute_metrics


def _result_from_equity(equity_values, positions=None, trades=None):
    idx = pd.date_range("2026-01-05", periods=len(equity_values), freq="1D")
    equity = pd.Series(equity_values, index=idx)
    positions = positions if positions is not None else pd.Series(1, index=idx)
    bars = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, index=idx)
    return BacktestResult(
        strategy_name="Test", instrument="TEST", bars=bars, signals=positions,
        positions=positions, equity_curve=equity, trades=trades or [],
    )


def test_total_return_and_win_rate():
    equity = [10_000, 10_500, 10_200, 11_000]
    trades = [
        Trade(pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-06"), 1, 100, 105, 10, 50, 5, 45, 10_000),
        Trade(pd.Timestamp("2026-01-06"), pd.Timestamp("2026-01-07"), 1, 105, 102, 10, -30, 5, -35, 10_500),
    ]
    result = _result_from_equity(equity, trades=trades)
    metrics = compute_metrics(result, initial_capital=10_000)

    assert metrics["total_return"] == pytest_approx(0.10)
    assert metrics["num_trades"] == 2
    assert metrics["win_rate"] == 0.5


def test_max_drawdown_is_negative_and_correct():
    equity = [10_000, 12_000, 9_000, 11_000]
    result = _result_from_equity(equity)
    metrics = compute_metrics(result, initial_capital=10_000)
    # peak 12000 -> trough 9000 => drawdown = (9000-12000)/12000 = -0.25
    assert metrics["max_drawdown"] == pytest_approx(-0.25)


def test_short_span_does_not_produce_absurd_cagr():
    # Two 1-minute bars: total_return is real, but annualizing 2 minutes of
    # data must not be reported as a meaningful CAGR.
    idx = pd.date_range("2026-01-05 09:30:00", periods=2, freq="1min")
    equity = pd.Series([10_000, 10_100], index=idx)
    bars = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, index=idx)
    result = BacktestResult(
        strategy_name="Test", instrument="TEST", bars=bars, signals=pd.Series(0, index=idx),
        positions=pd.Series(0, index=idx), equity_curve=equity, trades=[],
    )
    metrics = compute_metrics(result, initial_capital=10_000, freq_hint="1min")
    assert np.isnan(metrics["cagr"])
    assert metrics["total_return"] == pytest_approx(0.01)


def pytest_approx(x):
    import pytest
    return pytest.approx(x)
