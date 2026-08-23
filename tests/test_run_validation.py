import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from scripts.run_validation import main, parse_args
from src.backtest.strategies.base import Strategy


def _bars_csv(path, n=300, seed=0):
    rng = np.random.default_rng(seed)
    trend = np.concatenate([np.linspace(100.0, 200.0, n // 2), np.linspace(200.0, 100.0, n - n // 2)])
    close = trend + rng.normal(0, 0.5, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    bars = pd.DataFrame({
        "open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 1000.0,
    }, index=idx)
    bars.reset_index(names="timestamp").to_csv(path, index=False)


class TinyStrategy(Strategy):
    PARAM_SPACE = {"level": [95, 105]}

    @property
    def name(self):
        return f"Tiny({self.params.get('level', 100)})"

    def generate_signals(self, bars):
        level = self.params.get("level", 100)
        return (bars["close"] > level).astype(int)


def test_parse_args_applies_defaults():
    args = parse_args(["--data", "bars.csv:BTC_USDT"])
    assert args.data == "bars.csv:BTC_USDT"
    assert args.freq == "5min"
    assert args.n_folds == 5
    assert args.capital == 100_000.0
    assert args.output == "reports/validation"


def test_main_writes_all_four_reports_for_a_small_strategy_list(tmp_path, monkeypatch):
    import scripts.run_validation as run_validation

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(run_validation, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    main(["--data", "bars_test.csv:MES", "--freq", "1D", "--output", "reports/validation"])

    out_dir = "reports/validation"
    for fname in ["walkforward_summary.csv", "walkforward_folds.csv", "sensitivity_summary.csv", "sensitivity_detail.csv"]:
        assert os.path.exists(os.path.join(out_dir, fname))

    wf_summary = pd.read_csv(os.path.join(out_dir, "walkforward_summary.csv"))
    assert list(wf_summary["strategy"]) == ["TinyStrategy"]
    assert wf_summary["n_folds"].iloc[0] == 5

    sens_detail = pd.read_csv(os.path.join(out_dir, "sensitivity_detail.csv"))
    assert set(sens_detail["strategy"]) == {"TinyStrategy"}
    assert len(sens_detail) == 2  # one PARAM_SPACE entry, two candidate values


def test_main_splits_the_data_argument_on_the_last_colon():
    # Windows-style or otherwise colon-bearing paths shouldn't confuse the
    # split - only the trailing ":SYMBOL" should be peeled off.
    args = parse_args(["--data", "C:/data/bars.csv:BTC_USDT"])
    path, symbol = args.data.rsplit(":", 1)
    assert path == "C:/data/bars.csv"
    assert symbol == "BTC_USDT"


def test_main_still_writes_a_sensitivity_report_when_walkforward_has_too_little_data(tmp_path, monkeypatch):
    import scripts.run_validation as run_validation

    monkeypatch.chdir(tmp_path)
    _bars_csv("tiny_bars.csv", n=20)  # too few bars for the default 5-fold walk-forward
    monkeypatch.setattr(run_validation, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    main(["--data", "tiny_bars.csv:MES", "--freq", "1D", "--output", "reports/validation"])  # must not raise

    out_dir = "reports/validation"
    # Every strategy's walk-forward was skipped, so wf_summary_rows was empty -
    # pandas writes that as a headerless near-empty file rather than a CSV
    # with real columns and zero data rows, so it can't be read back with
    # pd.read_csv (EmptyDataError).
    with open(os.path.join(out_dir, "walkforward_summary.csv")) as f:
        assert f.read().strip() == ""

    sens_detail = pd.read_csv(os.path.join(out_dir, "sensitivity_detail.csv"))
    assert len(sens_detail) == 2  # sensitivity has no fold-length requirement, so it still ran
