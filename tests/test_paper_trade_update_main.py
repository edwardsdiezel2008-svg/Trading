import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from scripts.paper_trade_update import main
from src.backtest.strategies import ALL_STRATEGY_CLASSES


def _write_bars_csv(path, n=200, seed=0):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    prices = np.maximum(prices, 1.0)
    idx = pd.date_range("2026-01-05", periods=n, freq="1D")
    bars = pd.DataFrame({"open": prices, "high": prices + 0.5, "low": prices - 0.5, "close": prices, "volume": 1000}, index=idx)
    bars.reset_index(names="timestamp").to_csv(path, index=False)


def test_main_unleveraged_writes_positions_trade_log_and_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "paper_trading").mkdir()
    _write_bars_csv(tmp_path / "paper_trading" / "bars.csv")

    main(["--freq", "1D", "--tracking-start", "2026-01-10", "--symbol", "BTC_USDT"])

    positions_path = tmp_path / "paper_trading" / "positions.json"
    assert positions_path.exists()
    with open(positions_path) as f:
        positions = json.load(f)

    assert positions["symbol"] == "BTC_USDT"
    assert positions["leverage"] == 1.0
    assert set(positions["strategies"].keys()) == {cls().name for cls in ALL_STRATEGY_CLASSES}
    for entry in positions["strategies"].values():
        assert entry["position_label"] in {"LONG", "SHORT", "FLAT"}
        assert "liquidation_price" not in entry  # only present for leveraged tracks
        assert isinstance(entry["equity_curve"], list) and entry["equity_curve"]

    assert (tmp_path / "paper_trading" / "trade_log.csv").exists()
    assert (tmp_path / "paper_trading" / "summary.md").exists()
    assert "Buy & Hold" in capsys.readouterr().out


def test_main_leveraged_track_adds_liquidation_and_funding_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "paper_trading").mkdir()
    _write_bars_csv(tmp_path / "paper_trading" / "bars_perp.csv")
    with open(tmp_path / "paper_trading" / "btc_market_snapshot.json", "w") as f:
        json.dump({"funding_rate": {"rate": 0.0001}}, f)

    main([
        "--suffix", "_perp", "--freq", "1D", "--tracking-start", "2026-01-10",
        "--symbol", "BTC_USDT", "--leverage", "3.0",
        "--bars-file", "paper_trading/bars_perp.csv",
    ])

    with open(tmp_path / "paper_trading" / "positions_perp.json") as f:
        positions = json.load(f)

    assert positions["leverage"] == 3.0
    for entry in positions["strategies"].values():
        assert "funding_accrued_usd" in entry
        assert "funding_last_accrued_utc" in entry
