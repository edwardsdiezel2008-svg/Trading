import json
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, ".")

from scripts.walkforward_snapshot import main, parse_args
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


class NoGridStrategy(Strategy):
    def generate_signals(self, bars):
        return pd.Series(0, index=bars.index)


def test_parse_args_applies_defaults_and_parses_leverage():
    args = parse_args(["--bars", "b.csv", "--symbol", "BTC_USDT", "--output", "out.json", "--leverage", "3.0"])
    assert args.bars == "b.csv"
    assert args.symbol == "BTC_USDT"
    assert args.freq == "1D"
    assert args.n_folds == 5
    assert args.capital == 100_000.0
    assert args.leverage == 3.0


def test_main_writes_the_walkforward_json_for_a_small_strategy_list(tmp_path, monkeypatch):
    import scripts.walkforward_snapshot as walkforward_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(walkforward_snapshot, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    main(["--bars", "bars_test.csv", "--symbol", "MES", "--output", "wf.json"])

    with open("wf.json") as f:
        out = json.load(f)

    assert out["symbol"] == "MES"
    assert out["n_folds"] == 5
    assert len(out["results"]) == 1
    r = out["results"][0]
    assert r["strategy"] == TinyStrategy().name
    assert "oos_total_return" in r
    assert "oos_significant" in r
    assert r["n_folds"] == 5


def test_main_records_an_error_entry_for_a_strategy_with_no_param_space(tmp_path, monkeypatch):
    import scripts.walkforward_snapshot as walkforward_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(walkforward_snapshot, "ALL_STRATEGY_CLASSES", [NoGridStrategy])

    main(["--bars", "bars_test.csv", "--symbol", "MES", "--output", "wf.json"])  # must not raise

    with open("wf.json") as f:
        out = json.load(f)

    assert len(out["results"]) == 1
    assert "error" in out["results"][0]
    assert out["results"][0]["strategy"] == NoGridStrategy().name


def test_main_applies_leverage_kwargs_to_run_walk_forward(tmp_path, monkeypatch):
    import scripts.walkforward_snapshot as walkforward_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(walkforward_snapshot, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    seen_kwargs = {}
    real_run_walk_forward = walkforward_snapshot.run_walk_forward

    def spy(bars, cls, spec, n_folds, initial_capital, freq_hint, **kwargs):
        seen_kwargs.update(kwargs)
        return real_run_walk_forward(bars, cls, spec, n_folds=n_folds, initial_capital=initial_capital, freq_hint=freq_hint, **kwargs)

    monkeypatch.setattr(walkforward_snapshot, "run_walk_forward", spy)

    main(["--bars", "bars_test.csv", "--symbol", "BTCUSD-PERP", "--output", "wf.json", "--leverage", "3.0"])

    assert seen_kwargs["capital_fraction"] == 3.0
    assert "max_loss_fraction" in seen_kwargs
