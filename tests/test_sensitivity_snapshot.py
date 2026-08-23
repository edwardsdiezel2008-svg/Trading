import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from scripts.sensitivity_snapshot import main, parse_args
from src.backtest.strategies.base import Strategy


def _bars_csv(path, n=100, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    close = np.maximum(close, 1.0)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    bars = pd.DataFrame({
        "open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 1000.0,
    }, index=idx)
    bars.reset_index(names="timestamp").to_csv(path, index=False)


class TinyStrategy(Strategy):
    PARAM_SPACE = {"level": [95, 100, 105]}

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
    assert args.capital == 100_000.0
    assert args.leverage == 3.0


def test_main_writes_the_sensitivity_json_for_a_small_strategy_list(tmp_path, monkeypatch):
    import scripts.sensitivity_snapshot as sensitivity_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(sensitivity_snapshot, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    main(["--bars", "bars_test.csv", "--symbol", "MES", "--output", "sens.json"])

    with open("sens.json") as f:
        out = json.load(f)

    assert out["symbol"] == "MES"
    assert len(out["results"]) == 1
    r = out["results"][0]
    assert r["strategy"] == TinyStrategy().name
    assert r["n_values_tested"] == 3  # one PARAM_SPACE value: 3 candidates
    assert 0.0 <= r["frac_profitable"] <= 1.0
    assert r["sharpe_min"] <= r["sharpe_max"]


def test_main_records_an_error_entry_for_a_strategy_with_no_param_space(tmp_path, monkeypatch):
    import scripts.sensitivity_snapshot as sensitivity_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(sensitivity_snapshot, "ALL_STRATEGY_CLASSES", [NoGridStrategy])

    main(["--bars", "bars_test.csv", "--symbol", "MES", "--output", "sens.json"])  # must not raise

    with open("sens.json") as f:
        out = json.load(f)

    assert len(out["results"]) == 1
    assert "error" in out["results"][0]
    assert out["results"][0]["strategy"] == NoGridStrategy().name


def test_main_uses_leverage_based_liquidation_floor_instead_of_the_flat_default(tmp_path, monkeypatch):
    import scripts.sensitivity_snapshot as sensitivity_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(sensitivity_snapshot, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    seen_kwargs = {}
    real_param_sensitivity = sensitivity_snapshot.param_sensitivity

    def spy(bars, cls, spec, freq_hint, initial_capital, **kwargs):
        seen_kwargs.update(kwargs)
        return real_param_sensitivity(bars, cls, spec, freq_hint=freq_hint, initial_capital=initial_capital, **kwargs)

    monkeypatch.setattr(sensitivity_snapshot, "param_sensitivity", spy)

    main(["--bars", "bars_test.csv", "--symbol", "BTCUSD-PERP", "--output", "sens.json", "--leverage", "3.0"])

    assert seen_kwargs["capital_fraction"] == 3.0
    assert seen_kwargs["max_loss_fraction"] != sensitivity_snapshot.MAX_LOSS_FRACTION


def test_main_uses_the_flat_default_liquidation_floor_without_leverage(tmp_path, monkeypatch):
    import scripts.sensitivity_snapshot as sensitivity_snapshot

    monkeypatch.chdir(tmp_path)
    _bars_csv("bars_test.csv")
    monkeypatch.setattr(sensitivity_snapshot, "ALL_STRATEGY_CLASSES", [TinyStrategy])

    seen_kwargs = {}
    real_param_sensitivity = sensitivity_snapshot.param_sensitivity

    def spy(bars, cls, spec, freq_hint, initial_capital, **kwargs):
        seen_kwargs.update(kwargs)
        return real_param_sensitivity(bars, cls, spec, freq_hint=freq_hint, initial_capital=initial_capital, **kwargs)

    monkeypatch.setattr(sensitivity_snapshot, "param_sensitivity", spy)

    main(["--bars", "bars_test.csv", "--symbol", "MES", "--output", "sens.json"])

    assert seen_kwargs["max_loss_fraction"] == sensitivity_snapshot.MAX_LOSS_FRACTION
    assert seen_kwargs["capital_fraction"] == 1.0
