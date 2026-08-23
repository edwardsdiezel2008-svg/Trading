import sys

import pandas as pd
import pytest

sys.path.insert(0, ".")

from scripts.survivor_stress_test import (
    _annualized_sharpe,
    pd_isna,
    portfolio_analysis,
    select_largest_frequency_group,
)


def test_pd_isna_detects_nan_and_passes_through_normal_values():
    assert pd_isna(float("nan")) is True
    assert pd_isna(0.0) is False
    assert pd_isna(-1.5) is False


def test_annualized_sharpe_nan_below_two_points():
    assert _annualized_sharpe(pd.Series([0.01])).__ne__(_annualized_sharpe(pd.Series([0.01])))  # NaN != NaN


def test_annualized_sharpe_nan_when_returns_never_vary():
    # Zero-variance returns would divide-by-zero the Sharpe ratio - must
    # come back NaN, not raise or return inf.
    flat = pd.Series([0.001, 0.001, 0.001, 0.001])
    assert _annualized_sharpe(flat) != _annualized_sharpe(flat)


def test_annualized_sharpe_positive_for_a_rising_series_with_variance():
    returns = pd.Series([0.02, 0.01, 0.03, 0.015, 0.025])
    assert _annualized_sharpe(returns) > 0


def test_portfolio_analysis_returns_a_note_when_too_few_overlapping_bars():
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    curves = {
        "A": pd.Series([100000.0, 101000, 102000, 101500, 103000], index=idx),
        "B": pd.Series([100000.0, 99000, 98500, 99500, 100000], index=idx),
    }
    result = portfolio_analysis(curves)
    assert "note" in result


def _compound_curve(index, returns_seq, start=100000.0):
    equity = [start]
    for r in returns_seq:
        equity.append(equity[-1] * (1 + r))
    return pd.Series(equity, index=index)


def test_portfolio_analysis_computes_correlation_and_return_for_identical_survivors():
    idx = pd.date_range("2026-01-01", periods=12, freq="D")
    returns_seq = [0.01, -0.005, 0.02, -0.01, 0.015, 0.005, -0.02, 0.03, -0.015, 0.01, -0.005]
    curve = _compound_curve(idx, returns_seq)

    result = portfolio_analysis({"A": curve, "B": curve.copy()})

    assert result["aligned_bar_count"] == len(returns_seq)
    assert result["correlation_matrix"]["A"]["B"] == pytest.approx(1.0)
    assert result["mean_pairwise_correlation"] == pytest.approx(1.0)

    expected_total_return = curve.iloc[-1] / curve.iloc[0] - 1
    assert result["individual_aligned"]["A"]["total_return"] == pytest.approx(expected_total_return)
    # A and B are identical, so the equal-weighted portfolio return equals
    # each individual's own return - no diversification effect to measure.
    assert result["portfolio_total_return"] == pytest.approx(expected_total_return)


class _FakeStrategy:
    def __init__(self, name):
        self._name = name

    def __call__(self):
        return self

    @property
    def name(self):
        return self._name


def test_select_largest_frequency_group_picks_the_majority_frequency_and_excludes_others():
    # Mirrors the real SURVIVORS shape: 7 daily + 3 five-minute survivors.
    # Combining OOS equity curves across bar frequencies is meaningless (no
    # shared timestamps to align on), so this must pick daily (the larger
    # group) and drop the three 5-minute ones entirely.
    daily = _FakeStrategy("Daily_Strategy")
    intraday = _FakeStrategy("Intraday_Strategy")
    survivors = (
        [("Daily Track %d" % i, None, None, "1D", daily) for i in range(7)]
        + [("Intraday Track %d" % i, None, None, "5min", intraday) for i in range(3)]
    )
    curves = {
        f"{daily.name} / Daily Track {i}": pd.Series([1.0]) for i in range(7)
    }
    curves.update({
        f"{intraday.name} / Intraday Track {i}": pd.Series([1.0]) for i in range(3)
    })

    freq, selected = select_largest_frequency_group(survivors, curves)

    assert freq == "1D"
    assert len(selected) == 7
    assert all(key.startswith(daily.name) for key in selected)


def test_select_largest_frequency_group_keeps_everything_when_all_same_frequency():
    strat = _FakeStrategy("Only_Strategy")
    survivors = [(f"Track {i}", None, None, "1D", strat) for i in range(4)]
    curves = {f"{strat.name} / Track {i}": pd.Series([1.0]) for i in range(4)}

    freq, selected = select_largest_frequency_group(survivors, curves)

    assert freq == "1D"
    assert len(selected) == 4


def test_portfolio_analysis_aligns_on_the_intersection_of_differing_date_ranges():
    # A real cross-instrument case: two survivors' OOS windows don't start/
    # end on the same calendar day (different futures products' histories).
    # The inner join must truncate to exactly the overlapping window, not
    # pad or silently drop rows some other way.
    idx_a = pd.date_range("2026-01-01", periods=20, freq="D")
    idx_b = pd.date_range("2026-01-06", periods=20, freq="D")
    returns_a = [0.01 if i % 2 == 0 else -0.005 for i in range(19)]
    returns_b = [-0.008 if i % 3 == 0 else 0.012 for i in range(19)]
    curve_a = _compound_curve(idx_a, returns_a)
    curve_b = _compound_curve(idx_b, returns_b)

    result = portfolio_analysis({"A": curve_a, "B": curve_b})

    assert result["aligned_start"] == "2026-01-07"
    assert result["aligned_end"] == "2026-01-20"
    assert result["aligned_bar_count"] == 14


def test_run_one_produces_a_complete_stress_test_result_for_a_real_strategy(tmp_path, monkeypatch):
    import numpy as np

    from scripts.survivor_stress_test import run_one
    from src.backtest.strategies.trend import MovingAverageCrossover

    monkeypatch.chdir(tmp_path)
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    # Two clean trend regimes (up then down) with a little noise, so the
    # crossover strategy actually fires trades in both directions across
    # several walk-forward folds rather than sitting flat the whole test.
    rng = np.random.default_rng(0)
    trend = np.concatenate([np.linspace(100.0, 200.0, n // 2), np.linspace(200.0, 100.0, n - n // 2)])
    close = trend + rng.normal(0, 0.5, n)
    bars = pd.DataFrame({
        "open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 1000.0,
    }, index=idx)
    bars_path = "bars_test.csv"
    bars.reset_index(names="timestamp").to_csv(bars_path, index=False)

    result, oos_curve = run_one("Test Track", bars_path, "MES", "1D", MovingAverageCrossover)

    assert result["label"] == "Test Track"
    assert result["symbol"] == "MES"
    assert result["strategy"] == MovingAverageCrossover().name
    assert result["n_folds"] == 5
    assert 0 <= result["folds_positive"] <= result["n_folds"]
    assert len(result["fold_returns"]) == result["n_folds"]
    assert isinstance(result["normal_significant"], bool)
    assert isinstance(result["stressed_significant"], bool)
    # Cost-stressed OOS return should never beat the normal-cost run - 3x
    # slippage can only add friction, never remove it.
    assert result["stressed_oos_return"] <= result["normal_oos_return"] + 1e-9
    assert result["regime_breakdown"]  # at least one regime bucket attributed
    assert len(oos_curve) > 0


def test_main_writes_the_full_output_json_for_a_small_survivor_list(tmp_path, monkeypatch):
    import json

    import numpy as np

    import scripts.survivor_stress_test as survivor_stress_test
    from src.backtest.strategies.mean_reversion import RSIReversion
    from src.backtest.strategies.trend import MovingAverageCrossover

    monkeypatch.chdir(tmp_path)
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(1)
    trend = np.concatenate([np.linspace(100.0, 200.0, n // 2), np.linspace(200.0, 100.0, n - n // 2)])
    close = trend + rng.normal(0, 0.5, n)
    bars = pd.DataFrame({
        "open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 1000.0,
    }, index=idx)
    bars.reset_index(names="timestamp").to_csv("bars_test.csv", index=False)

    monkeypatch.setattr(survivor_stress_test, "SURVIVORS", [
        ("Test Track A", "bars_test.csv", "MES", "1D", MovingAverageCrossover),
        ("Test Track B", "bars_test.csv", "MES", "1D", RSIReversion),
    ])

    survivor_stress_test.main(["--output", "out.json"])

    with open("out.json") as f:
        out = json.load(f)

    assert len(out["results"]) == 2
    assert {r["label"] for r in out["results"]} == {"Test Track A", "Test Track B"}
    assert "generated_at_utc" in out
    # Both survivors share the "1D" frequency, so the portfolio step should
    # have run a real combination rather than falling back to the
    # too-few-overlapping-bars note.
    assert "note" not in out["portfolio_analysis"]
    assert "portfolio_total_return" in out["portfolio_analysis"]
