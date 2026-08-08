import pandas as pd
import pytest

from src.backtest.data_loader import load_bars, load_ticks, ticks_to_bars


def _write_tick_csv(tmp_path, rows):
    path = tmp_path / "ticks.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def test_load_ticks_autodetects_columns(tmp_path):
    path = _write_tick_csv(tmp_path, [
        {"Timestamp": "2026-01-05 09:30:00", "Price": 100.0, "Size": 10},
        {"Timestamp": "2026-01-05 09:30:01", "Price": 100.5, "Size": 5},
    ])
    ticks = load_ticks(path)
    assert list(ticks.columns) == ["price", "size"]
    assert ticks.index.is_monotonic_increasing
    assert ticks["price"].iloc[0] == 100.0


def test_load_ticks_missing_columns_raises(tmp_path):
    path = _write_tick_csv(tmp_path, [{"foo": 1, "bar": 2}])
    with pytest.raises(ValueError):
        load_ticks(path)


def test_ticks_to_bars_ohlc_correctness():
    idx = pd.to_datetime([
        "2026-01-05 09:30:00", "2026-01-05 09:30:20", "2026-01-05 09:30:40",
        "2026-01-05 09:31:05",
    ])
    ticks = pd.DataFrame({"price": [100.0, 102.0, 99.0, 105.0], "size": [1, 2, 3, 4]}, index=idx)
    bars = ticks_to_bars(ticks, freq="1min")

    assert len(bars) == 2
    first = bars.iloc[0]
    assert first["open"] == 100.0
    assert first["high"] == 102.0
    assert first["low"] == 99.0
    assert first["close"] == 99.0
    assert first["volume"] == 6

    second = bars.iloc[1]
    assert second["open"] == 105.0
    assert second["volume"] == 4


def test_load_bars_detects_already_bar_level_csv(tmp_path):
    path = tmp_path / "bars.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-05", periods=3, freq="1min"),
        "open": [1, 2, 3], "high": [1.5, 2.5, 3.5], "low": [0.5, 1.5, 2.5], "close": [1.2, 2.2, 3.2],
        "volume": [10, 20, 30],
    }).to_csv(path, index=False)

    bars = load_bars(str(path))
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert len(bars) == 3


def test_load_bars_resamples_raw_ticks(tmp_path):
    path = tmp_path / "ticks.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-05 09:30:00", periods=200, freq="1s"),
        "price": [100.0 + 0.01 * i for i in range(200)],
        "size": [1] * 200,
    }).to_csv(path, index=False)

    bars = load_bars(str(path), freq="1min")
    assert set(bars.columns) == {"open", "high", "low", "close", "volume"}
    assert len(bars) >= 3
