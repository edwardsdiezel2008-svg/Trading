import numpy as np
import pandas as pd

from src.backtest.regime import classify_regimes


def test_strong_trend_is_classified_as_trending():
    n = 150
    price = np.linspace(100, 300, n)  # clean, strong uptrend
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    bars = pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 100}, index=idx)

    regimes = classify_regimes(bars, adx_period=14)
    tail = regimes["trend_regime"].iloc[-30:]
    assert (tail == "trending").mean() > 0.8


def test_flat_noisy_price_is_classified_as_ranging():
    rng = np.random.default_rng(0)
    n = 150
    price = 100 + rng.normal(0, 0.3, n).cumsum() * 0  # exactly flat
    price = 100 + rng.normal(0, 0.05, n)  # tiny noise around a constant level
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    bars = pd.DataFrame({"open": price, "high": price + 0.05, "low": price - 0.05, "close": price, "volume": 100}, index=idx)

    regimes = classify_regimes(bars, adx_period=14)
    tail = regimes["trend_regime"].iloc[-30:]
    assert (tail == "ranging").mean() > 0.8


def test_regime_label_is_combination_of_trend_and_vol():
    n = 150
    price = np.linspace(100, 300, n)
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    bars = pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 100}, index=idx)

    regimes = classify_regimes(bars)
    valid = regimes.dropna(subset=["regime"])
    for label, row in zip(valid["regime"], valid.itertuples()):
        assert label == f"{row.trend_regime}/{row.vol_regime}"


def _flat_result(idx, equity, positions=None):
    from src.backtest.engine import BacktestResult

    bars = pd.DataFrame({"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1}, index=idx)
    positions = positions if positions is not None else pd.Series(1, index=idx)
    return BacktestResult(
        strategy_name="Test", instrument="TEST", bars=bars, signals=positions,
        positions=positions, equity_curve=pd.Series(equity, index=idx), trades=[],
    )


def test_explain_result_reports_not_enough_data_when_no_bar_has_a_classified_regime():
    from src.backtest.regime import explain_result

    idx = pd.date_range("2026-01-05", periods=5, freq="1min")
    result = _flat_result(idx, [10_000, 10_100, 10_050, 10_200, 10_150])
    # A "regimes" frame with every bar unclassified (as classify_regimes
    # produces during its own warmup period) - attribute_performance should
    # drop every row, leaving nothing to attribute.
    regimes = pd.DataFrame({"regime": [np.nan] * 5, "trend_regime": [np.nan] * 5, "vol_regime": [np.nan] * 5}, index=idx)

    summary = explain_result(result, regimes)
    assert summary == "Test on TEST: not enough data to classify regimes."


def test_explain_result_reports_the_best_and_worst_regime_when_they_differ():
    from src.backtest.regime import explain_result

    idx = pd.date_range("2026-01-05", periods=4, freq="1min")
    # Bar-over-bar equity deltas: +100, -50, +200 (bar 0's diff is NaN -> 0),
    # bucketed one bar each into "up" (bars 0-1) then "down" (bars 2-3), so
    # "down" nets +150 total and "up" nets +100 - "down" should be reported
    # as the best regime, "up" as the worst.
    result = _flat_result(idx, [10_000, 10_100, 10_050, 10_250])
    regimes = pd.DataFrame({
        "regime": ["up", "up", "down", "down"],
        "trend_regime": ["trending"] * 4, "vol_regime": ["low_vol"] * 4,
    }, index=idx)

    summary = explain_result(result, regimes)
    assert "Best regime: 'down'" in summary
    assert "Worst regime: 'up'" in summary
    assert "Test on TEST: net P&L $250" in summary
