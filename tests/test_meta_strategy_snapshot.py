import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from scripts.meta_strategy_snapshot import main, parse_args
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


class AlwaysLong(Strategy):
    @property
    def name(self):
        return "AlwaysLong"

    def generate_signals(self, bars):
        return pd.Series(1, index=bars.index)


class AlwaysFlat(Strategy):
    @property
    def name(self):
        return "AlwaysFlat"

    def generate_signals(self, bars):
        return pd.Series(0, index=bars.index)


def test_parse_args_applies_defaults_and_parses_leverage():
    args = parse_args(["--bars", "b.csv", "--symbol", "BTC_USDT", "--output", "out.json", "--leverage", "3.0"])
    assert args.bars == "b.csv"
    assert args.freq == "1D"
    assert args.n_folds == 5
    assert args.min_regime_bars == 20
    assert args.leverage == 3.0


def test_main_writes_the_meta_strategy_json_for_a_small_strategy_list(tmp_path, monkeypatch):
    import scripts.meta_strategy_snapshot as meta_strategy_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(meta_strategy_snapshot, "ALL_STRATEGY_CLASSES", [AlwaysLong, AlwaysFlat])

    main(["--bars", "bars_test.csv", "--symbol", "MES", "--output", "meta.json"])

    with open("meta.json") as f:
        out = json.load(f)

    assert out["symbol"] == "MES"
    assert "error" not in out
    assert "current_regime" in out
    assert "recommended_strategy" in out
    assert isinstance(out["live_regime_map"], dict)
    assert "total_return" in out["oos_metrics"]
    assert len(out["folds"]) == 5
    for f in out["folds"]:
        assert "regime_map" in f
        assert "test_total_return" in f


def test_main_writes_an_error_entry_when_there_is_too_little_data_for_the_folds(tmp_path, monkeypatch):
    import scripts.meta_strategy_snapshot as meta_strategy_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("tiny_bars.csv", n=20)  # far too few bars for the default 5 folds
    monkeypatch.setattr(meta_strategy_snapshot, "ALL_STRATEGY_CLASSES", [AlwaysLong, AlwaysFlat])

    main(["--bars", "tiny_bars.csv", "--symbol", "MES", "--output", "meta.json"])  # must not raise

    with open("meta.json") as f:
        out = json.load(f)

    assert "error" in out
    assert out["symbol"] == "MES"


def test_main_applies_leverage_kwargs_to_run_meta_strategy_walkforward(tmp_path, monkeypatch):
    import scripts.meta_strategy_snapshot as meta_strategy_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(meta_strategy_snapshot, "ALL_STRATEGY_CLASSES", [AlwaysLong, AlwaysFlat])

    seen_kwargs = {}
    real_fn = meta_strategy_snapshot.run_meta_strategy_walkforward

    def spy(bars, strategy_classes, spec, n_folds, min_regime_bars, initial_capital, freq_hint, **kwargs):
        seen_kwargs.update(kwargs)
        return real_fn(bars, strategy_classes, spec, n_folds=n_folds, min_regime_bars=min_regime_bars,
                        initial_capital=initial_capital, freq_hint=freq_hint, **kwargs)

    monkeypatch.setattr(meta_strategy_snapshot, "run_meta_strategy_walkforward", spy)

    main(["--bars", "bars_test.csv", "--symbol", "BTCUSD-PERP", "--output", "meta.json", "--leverage", "3.0"])

    assert seen_kwargs["capital_fraction"] == 3.0
    assert "max_loss_fraction" in seen_kwargs
