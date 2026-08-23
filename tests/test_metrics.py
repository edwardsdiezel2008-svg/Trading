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


def test_annualization_factor_falls_back_to_252_with_fewer_than_two_bars_and_no_freq_hint():
    from src.backtest.metrics import _annualization_factor

    idx = pd.date_range("2026-01-05", periods=1, freq="1min")
    bars = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, index=idx)

    assert _annualization_factor(bars, freq_hint=None) == 252.0


def test_annualization_factor_falls_back_to_252_when_the_median_gap_is_zero():
    from src.backtest.metrics import _annualization_factor

    # Duplicate/out-of-order timestamps collapse the median gap to zero -
    # dividing trading_seconds_per_year by that would raise ZeroDivisionError
    # rather than a graceful fallback.
    idx = pd.DatetimeIndex(["2026-01-05", "2026-01-05", "2026-01-05"])
    bars = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, index=idx)

    assert _annualization_factor(bars, freq_hint=None) == 252.0


def test_annualization_factor_infers_from_real_bar_spacing_without_a_freq_hint():
    from src.backtest.metrics import _annualization_factor

    idx = pd.date_range("2026-01-05", periods=5, freq="1h")
    bars = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, index=idx)

    factor = _annualization_factor(bars, freq_hint=None)
    assert factor == pytest_approx(252 * 6.5)  # hourly bars over a 6.5h session
