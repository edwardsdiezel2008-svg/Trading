import os

import numpy as np
import pandas as pd
import pytest

from src.backtest.cli import main, parse_args


def _write_bars_csv(path, n=150, seed=0):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    prices = np.maximum(prices, 1.0)
    idx = pd.date_range("2026-01-05", periods=n, freq="1D")
    bars = pd.DataFrame({"open": prices, "high": prices + 0.5, "low": prices - 0.5, "close": prices, "volume": 1000}, index=idx)
    bars.reset_index(names="timestamp").to_csv(path, index=False)


def test_parse_args_accepts_multiple_data_entries_and_applies_defaults():
    args = parse_args(["--data", "a.csv:AAPL", "b.csv:ES"])
    assert args.data == ["a.csv:AAPL", "b.csv:ES"]
    assert args.freq == "1min"
    assert args.capital == 100_000.0
    assert args.output == "reports"


def test_main_rejects_a_data_entry_without_a_colon(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_bars_csv(csv_path)
    with pytest.raises(SystemExit, match="must be 'path:SYMBOL'"):
        main(["--data", str(csv_path), "--freq", "1D"])


def test_main_runs_end_to_end_and_writes_the_report(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_bars_csv(csv_path)
    output_dir = str(tmp_path / "out")

    main(["--data", f"{csv_path}:AAPL", "--freq", "1D", "--output", output_dir])

    assert os.path.exists(os.path.join(output_dir, "metrics.csv"))
    assert os.path.exists(os.path.join(output_dir, "equity_curves.png"))
    assert os.path.exists(os.path.join(output_dir, "explanations.txt"))

    out = capsys.readouterr().out
    assert "Full report written to" in out
    assert output_dir in out
