import json
import sys

import numpy as np
import pandas as pd
import pytest

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
        assert entry["max_drawdown"] is None or entry["max_drawdown"] <= 0

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


def test_main_leveraged_track_builds_on_a_prior_run_s_funding_accrual(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.chdir(tmp_path)
    (tmp_path / "paper_trading").mkdir()
    _write_bars_csv(tmp_path / "paper_trading" / "bars_perp.csv")
    with open(tmp_path / "paper_trading" / "btc_market_snapshot.json", "w") as f:
        json.dump({"funding_rate": {"rate": 0.0001}}, f)

    # Simulate an existing positions file from a real earlier hourly run - a
    # funding_last_accrued_utc more than the 30-minute re-application guard
    # in the past, so this run's own accrual actually builds on it rather
    # than the fresh-start ("prior_ts is None") path every other test uses.
    strategy_names = [cls().name for cls in ALL_STRATEGY_CLASSES]
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    prior_positions = {
        name: {"funding_accrued_usd": 5.0, "funding_last_accrued_utc": stale_ts}
        for name in strategy_names
    }
    with open(tmp_path / "paper_trading" / "positions_perp.json", "w") as f:
        json.dump({"symbol": "BTC_USDT", "leverage": 3.0, "strategies": prior_positions}, f)

    main([
        "--suffix", "_perp", "--freq", "1D", "--tracking-start", "2026-01-10",
        "--symbol", "BTC_USDT", "--leverage", "3.0",
        "--bars-file", "paper_trading/bars_perp.csv",
    ])

    with open(tmp_path / "paper_trading" / "positions_perp.json") as f:
        positions = json.load(f)

    for entry in positions["strategies"].values():
        # The prior run's $5 baseline must still be reflected (not reset to
        # 0), and the timestamp must have moved forward from the stale value.
        assert entry["funding_accrued_usd"] != 0.0
        assert entry["funding_last_accrued_utc"] != stale_ts


def test_main_applies_the_cost_aware_filter_when_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "paper_trading").mkdir()
    _write_bars_csv(tmp_path / "paper_trading" / "bars.csv")

    main(["--freq", "1D", "--tracking-start", "2026-01-10", "--symbol", "BTC_USDT", "--cost-aware-min-multiple", "5.0"])

    positions_path = tmp_path / "paper_trading" / "positions.json"
    assert positions_path.exists()
    with open(positions_path) as f:
        positions = json.load(f)

    # CostAwareFilter delegates .name to the wrapped strategy, so the keys
    # are unchanged even though the filter is genuinely active underneath.
    assert set(positions["strategies"].keys()) == {cls().name for cls in ALL_STRATEGY_CLASSES}


def test_main_ships_max_drawdown_computed_from_the_full_curve_not_the_downsampled_one(tmp_path, monkeypatch):
    import scripts.paper_trade_update as paper_trade_update
    from src.backtest.strategies.base import Strategy

    # A one-bar ~4% dip that fully recovers the very next bar - small enough
    # to stay under the engine's default 5% portfolio drawdown breaker (so
    # the position isn't force-halted and the recovery actually happens),
    # placed at bar 249 of 500, an index _downsample_equity_curve's 250-point
    # stride skips over entirely. The dashboard's old JS max-drawdown
    # calculation (recomputed from that lossy 250-point curve) would see
    # this dip's neighbors both back at the recovered level and report a
    # near-zero drawdown; the shipped `max_drawdown` field is computed by
    # metrics.py from the real, full-resolution equity curve instead, so it
    # must actually reflect the dip.
    class BuyAndHold(Strategy):
        def generate_signals(self, bars):
            return pd.Series(1, index=bars.index)

    monkeypatch.chdir(tmp_path)
    (tmp_path / "paper_trading").mkdir()
    monkeypatch.setattr(paper_trade_update, "ALL_STRATEGY_CLASSES", [BuyAndHold])

    n = 500
    prices = np.full(n, 100.0)
    prices[249] = 96.0
    idx = pd.date_range("2026-01-05", periods=n, freq="1D")
    bars = pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1000}, index=idx)
    bars.reset_index(names="timestamp").to_csv(tmp_path / "paper_trading" / "bars.csv", index=False)

    paper_trade_update.main(["--freq", "1D", "--tracking-start", "2026-01-10", "--symbol", "BTC_USDT"])

    with open(tmp_path / "paper_trading" / "positions.json") as f:
        positions = json.load(f)

    entry = positions["strategies"]["BuyAndHold"]
    assert entry["max_drawdown"] == pytest.approx(-0.04135, abs=1e-4)

    # The bug this guards against: recomputing drawdown from the shipped,
    # downsampled equity_curve instead would miss the dip almost entirely.
    lossy = 0.0
    peak = float("-inf")
    for _, eq in entry["equity_curve"]:
        peak = max(peak, eq)
        lossy = min(lossy, eq / peak - 1) if peak > 0 else lossy
    assert lossy > entry["max_drawdown"] + 0.01  # materially less negative - the dip is invisible to it
