import os

import numpy as np
import pandas as pd

from src.backtest.report import run_comparison
from src.backtest.strategies.mean_reversion import RSIReversion
from src.backtest.strategies.trend import MovingAverageCrossover


def _bars(n=200, seed=0):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    prices = np.maximum(prices, 1.0)
    idx = pd.date_range("2026-01-05", periods=n, freq="1D")
    return pd.DataFrame({"open": prices, "high": prices + 0.5, "low": prices - 0.5, "close": prices, "volume": 1000}, index=idx)


def test_run_comparison_writes_report_files_and_returns_expected_shape(tmp_path):
    bars_by_symbol = {"AAPL": _bars(seed=1), "ES": _bars(seed=2)}
    strategies = [MovingAverageCrossover(), RSIReversion()]
    output_dir = str(tmp_path / "reports")

    out = run_comparison(bars_by_symbol, strategies=strategies, output_dir=output_dir)

    assert set(out.keys()) == {"metrics", "explanations", "results"}
    assert len(out["results"]) == len(bars_by_symbol) * len(strategies)
    assert len(out["metrics"]) == len(bars_by_symbol) * len(strategies)
    assert {"strategy", "instrument", "sharpe"}.issubset(out["metrics"].columns)

    assert os.path.exists(os.path.join(output_dir, "metrics.csv"))
    assert os.path.exists(os.path.join(output_dir, "equity_curves.png"))
    assert os.path.exists(os.path.join(output_dir, "explanations.txt"))

    with open(os.path.join(output_dir, "explanations.txt")) as f:
        explanations_on_disk = f.read()
    assert explanations_on_disk == out["explanations"]
    assert MovingAverageCrossover().name in explanations_on_disk
    assert "AAPL" in explanations_on_disk and "ES" in explanations_on_disk


def test_run_comparison_defaults_to_the_full_strategy_library_when_none_given(tmp_path):
    from src.backtest.strategies import ALL_STRATEGY_CLASSES

    out = run_comparison({"AAPL": _bars(seed=3)}, output_dir=str(tmp_path / "reports"))

    assert len(out["results"]) == len(ALL_STRATEGY_CLASSES)
