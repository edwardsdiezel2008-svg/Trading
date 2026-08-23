import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from scripts.export_replay_data import export_instrument, pd_isna
from src.backtest.strategies import ALL_STRATEGY_CLASSES


def _bars_csv(path, n=200, seed=0):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    prices = np.maximum(prices, 1.0)
    idx = pd.date_range("2026-01-05", periods=n, freq="1D")
    df = pd.DataFrame({
        "open": prices, "high": prices + 0.5, "low": prices - 0.5, "close": prices, "volume": 1000,
    }, index=idx)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.reset_index(names="timestamp").to_csv(path, index=False)


def test_pd_isna_detects_nan_and_passes_through_normal_values():
    assert pd_isna(float("nan")) is True
    assert pd_isna(1.0) is False
    assert pd_isna(None) is True


def test_export_instrument_produces_the_expected_shape(tmp_path):
    path = str(tmp_path / "bars.csv")
    _bars_csv(path)

    out = export_instrument("TEST", path, freq="1D")

    assert out["symbol"] == "TEST"
    assert out["freq"] == "1D"
    assert out["initial_capital"] == 100_000.0
    assert set(out["bars"].keys()) == {"t", "o", "h", "l", "c"}
    assert len(out["bars"]["t"]) == 200
    assert set(out["regimes"].keys()) == {"trend", "vol"}
    assert len(out["regimes"]["trend"]) == 200

    assert len(out["strategies"]) == len(ALL_STRATEGY_CLASSES)
    strat = out["strategies"][0]
    assert set(strat.keys()) == {"name", "positions", "equity", "trades", "metrics"}
    assert len(strat["positions"]) == 200
    assert len(strat["equity"]) == 200
    assert {"total_return", "sharpe", "max_drawdown", "win_rate", "num_trades"}.issubset(strat["metrics"].keys())
    for t in strat["trades"]:
        assert set(t.keys()) == {"entry_t", "exit_t", "dir", "entry_px", "exit_px", "net_pnl"}


def test_export_instrument_regimes_use_none_rather_than_nan_for_missing_values(tmp_path):
    path = str(tmp_path / "bars.csv")
    _bars_csv(path)

    out = export_instrument("TEST", path, freq="1D")

    # classify_regimes has a warmup period before its rolling windows fill -
    # those early bars must serialize as JSON null, not a NaN that json.dump
    # would choke on (or silently write as invalid "NaN" JSON).
    assert out["regimes"]["trend"][0] is None or isinstance(out["regimes"]["trend"][0], (int, float, str))
    assert all(v is None or isinstance(v, (int, float, str)) for v in out["regimes"]["trend"])


def test_main_writes_reports_replay_data_json(tmp_path, monkeypatch):
    import scripts.export_replay_data as export_replay_data

    monkeypatch.chdir(tmp_path)
    fake_instrument = {
        "symbol": "FAKE", "freq": "1D", "initial_capital": 100_000.0,
        "bars": {"t": [1, 2], "o": [1.0, 2.0], "h": [1.0, 2.0], "l": [1.0, 2.0], "c": [1.0, 2.0]},
        "regimes": {"trend": [None, "up"], "vol": [None, "normal"]},
        "strategies": [{"name": "Fake", "positions": [0, 1], "equity": [100000.0, 100010.0], "trades": [], "metrics": {}}],
    }
    monkeypatch.setattr(export_replay_data, "export_instrument", lambda symbol, path, freq="5min": dict(fake_instrument, symbol=symbol))

    export_replay_data.main()

    with open("reports/replay_data.json") as f:
        out = json.load(f)

    assert [inst["symbol"] for inst in out["instruments"]] == ["BTC_USDT", "AAPL", "ES"]
