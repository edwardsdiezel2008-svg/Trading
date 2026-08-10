"""Statistical significance for walk-forward out-of-sample results.

A walk-forward OOS total-return number is still a single point estimate
from one particular sequence of market history - it doesn't by itself say
whether that edge is distinguishable from noise given how much data actually
went into it. Circular block bootstrap resampling answers that directly:
resample the OOS per-bar returns in contiguous blocks (preserving the
series' own serial correlation - autocorrelated returns violate the i.i.d.
assumption a naive per-bar resample would need) many times, and look at the
resulting distribution of total returns. If the confidence interval still
includes zero, the OOS result can't be distinguished from a strategy with no
real edge at this sample size - even when the point estimate itself is
positive. This isn't a substitute for a rigorous hypothesis test (multiple
testing across 12 strategies isn't corrected for here, for one), just an
honest uncertainty band around a single point estimate that a bare walk-
forward number doesn't carry on its own.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def bootstrap_return_ci(
    equity_curve: pd.Series,
    n_bootstrap: int = 1000,
    block_size: int = 20,
    ci: float = 0.90,
    seed: int | None = 7,
) -> dict:
    """Circular block bootstrap on an equity curve's per-bar returns.

    block_size is in bars, not calendar time - 20 bars is ~1 month for a
    daily track or ~100 minutes for a 5-minute track. Larger blocks preserve
    more autocorrelation structure at the cost of fewer effectively-
    independent resampling units; 20 is a reasonable default for both
    frequencies used in this project, not something tuned per-track.

    Fully vectorized (no per-iteration Python loop): builds all n_bootstrap
    resamples as one array via fancy indexing into a circularly-padded
    returns array, so 1000 iterations over a several-thousand-bar OOS curve
    takes a fraction of a second.
    """
    returns = equity_curve.pct_change().dropna().to_numpy()
    n = len(returns)
    if n < 10:
        return {
            "point_estimate": None, "ci_low": None, "ci_high": None,
            "ci_level": ci, "significant": None, "n_bars": n,
            "note": "too few OOS bars for a meaningful bootstrap",
        }

    rng = np.random.default_rng(seed)
    block_size = max(1, min(block_size, n))  # requested block_size is clamped down, not a bailout condition
    n_blocks = -(-n // block_size)  # ceil division

    # Pad circularly so any start index in [0, n) plus block_size stays in-bounds.
    padded = np.concatenate([returns, returns[:block_size]])
    starts = rng.integers(0, n, size=(n_bootstrap, n_blocks))
    offsets = np.arange(block_size)
    idx = starts[:, :, None] + offsets[None, None, :]
    sampled = padded[idx].reshape(n_bootstrap, -1)[:, :n]
    totals = np.prod(1.0 + sampled, axis=1) - 1.0

    alpha = (1.0 - ci) / 2.0
    ci_low = float(np.quantile(totals, alpha))
    ci_high = float(np.quantile(totals, 1.0 - alpha))
    point_estimate = float(np.prod(1.0 + returns) - 1.0)

    return {
        "point_estimate": point_estimate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "ci_level": ci,
        "significant": bool(ci_low > 0.0),
        "n_bars": n,
    }
