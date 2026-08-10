import numpy as np
import pandas as pd

from src.backtest.significance import bootstrap_return_ci


def _equity_from_returns(returns, start=100_000.0):
    idx = pd.date_range("2026-01-01", periods=len(returns) + 1, freq="1D")
    equity = [start]
    for r in returns:
        equity.append(equity[-1] * (1.0 + r))
    return pd.Series(equity, index=idx)


def test_strong_constant_positive_drift_is_significant():
    returns = [0.005] * 300  # deterministic +0.5%/day, zero variance
    equity = _equity_from_returns(returns)
    result = bootstrap_return_ci(equity, n_bootstrap=200, block_size=20)
    assert result["point_estimate"] > 0
    assert result["ci_low"] > 0
    assert result["significant"] is True
    # Zero-variance input: every bootstrap resample reproduces the same
    # total return, so the interval collapses to a point.
    assert abs(result["ci_low"] - result["ci_high"]) < 1e-6
    assert abs(result["ci_low"] - result["point_estimate"]) < 1e-6


def test_zero_mean_noise_is_not_significant():
    rng = np.random.default_rng(42)
    returns = rng.normal(loc=0.0, scale=0.01, size=1000)
    equity = _equity_from_returns(returns)
    result = bootstrap_return_ci(equity, n_bootstrap=500, block_size=20, seed=1)
    assert result["ci_low"] < 0 < result["ci_high"]
    assert result["significant"] is False


def test_too_few_bars_returns_note_not_a_crash():
    equity = _equity_from_returns([0.01, -0.01, 0.02])
    result = bootstrap_return_ci(equity, block_size=20)
    assert result["point_estimate"] is None
    assert result["significant"] is None
    assert "note" in result


def test_ci_low_never_exceeds_ci_high():
    rng = np.random.default_rng(7)
    returns = rng.normal(loc=0.001, scale=0.02, size=500)
    equity = _equity_from_returns(returns)
    result = bootstrap_return_ci(equity, n_bootstrap=300, block_size=15)
    assert result["ci_low"] <= result["ci_high"]


def test_same_seed_is_reproducible():
    rng = np.random.default_rng(3)
    returns = rng.normal(loc=0.001, scale=0.015, size=400)
    equity = _equity_from_returns(returns)
    r1 = bootstrap_return_ci(equity, n_bootstrap=200, block_size=20, seed=99)
    r2 = bootstrap_return_ci(equity, n_bootstrap=200, block_size=20, seed=99)
    assert r1 == r2


def test_block_size_larger_than_series_is_clamped_not_a_crash():
    # A block_size (1000) far exceeding the series length (25) is clamped
    # down to the series length rather than crashing or bailing out - the
    # "too few bars" guard is about absolute series length, not block_size.
    returns = [0.01] * 25
    equity = _equity_from_returns(returns)
    result = bootstrap_return_ci(equity, n_bootstrap=50, block_size=1000)
    assert result["point_estimate"] is not None
    assert result["ci_low"] is not None
