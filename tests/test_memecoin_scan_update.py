import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, ".")

from scripts.memecoin_scan_update import MIN_BARS, _atr, scan_coin


def _write_bars_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df.to_csv(path, index=False)


def _hourly_timestamps(n):
    return [f"2026-01-01T{i:02d}:00:00" if i < 24 else f"2026-01-{2 + i // 24:02d}T{i % 24:02d}:00:00" for i in range(n)]


def test_scan_coin_returns_none_when_the_bars_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert scan_coin("NOPE") is None


def test_scan_coin_reports_insufficient_data_below_the_minimum_bar_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    n = MIN_BARS - 1
    rows = [[ts, 1.0, 1.1, 0.9, 1.0, 100] for ts in _hourly_timestamps(n)]
    _write_bars_csv("paper_trading/memecoins/TESTUSD.csv", rows)

    result = scan_coin("TESTUSD")
    assert result["status"] == "insufficient_data"
    assert result["bar_count"] == n
    assert result["min_bars_needed"] == MIN_BARS


def test_scan_coin_flags_a_breakout_above_the_prior_20_bar_high(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    n = MIN_BARS + 5
    timestamps = _hourly_timestamps(n)
    # Flat range at price 1.0 for every bar except the last, which spikes
    # well above the prior 20-bar high of 1.0.
    rows = [[ts, 1.0, 1.02, 0.98, 1.0, 100] for ts in timestamps[:-1]]
    rows.append([timestamps[-1], 1.0, 1.5, 1.0, 1.5, 100])
    _write_bars_csv("paper_trading/memecoins/TESTUSD.csv", rows)

    result = scan_coin("TESTUSD")
    assert result["status"] == "ok"
    assert result["is_breakout"] is True
    assert result["prior_20bar_high"] == pytest.approx(1.02)
    assert result["breakout_pct"] > 0
    assert result["breakout_strength_atr"] > 0


def test_scan_coin_does_not_flag_a_breakout_when_price_stays_in_range(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    n = MIN_BARS + 5
    rows = [[ts, 1.0, 1.02, 0.98, 1.0, 100] for ts in _hourly_timestamps(n)]
    _write_bars_csv("paper_trading/memecoins/TESTUSD.csv", rows)

    result = scan_coin("TESTUSD")
    assert result["status"] == "ok"
    assert result["is_breakout"] is False
    assert result["breakout_pct"] <= 0


def test_scan_coin_computes_drawdown_from_the_full_history_high(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    n = MIN_BARS + 5
    timestamps = _hourly_timestamps(n)
    # Peaks mid-history at 2.0, then grinds down to 1.0 by the last bar -
    # the window high must come from the whole series, not just the recent
    # lookback window used for the breakout check.
    rows = []
    for i, ts in enumerate(timestamps):
        price = 2.0 if i == 5 else 1.0
        rows.append([ts, price, price, price, price, 100])
    _write_bars_csv("paper_trading/memecoins/TESTUSD.csv", rows)

    result = scan_coin("TESTUSD")
    assert result["window_high"] == pytest.approx(2.0)
    assert result["drawdown_from_window_high_pct"] == pytest.approx((1.0 / 2.0 - 1) * 100)


def test_atr_is_nan_before_the_warmup_period_and_positive_after():
    idx = pd.date_range("2026-01-01", periods=20, freq="h")
    bars = pd.DataFrame({
        "high": [10 + (i % 3) for i in range(20)],
        "low": [8 - (i % 2) for i in range(20)],
        "close": [9 + (i % 3) for i in range(20)],
    }, index=idx)
    atr = _atr(bars, period=14)
    assert atr.iloc[:13].isna().all()
    assert atr.iloc[13:].notna().all()
    assert (atr.iloc[13:] > 0).all()
