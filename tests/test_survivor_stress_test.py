import sys

import pandas as pd
import pytest

sys.path.insert(0, ".")

from scripts.survivor_stress_test import _annualized_sharpe, pd_isna, portfolio_analysis


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
