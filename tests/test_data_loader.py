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


def test_load_bars_raises_when_no_timestamp_column_is_identifiable(tmp_path):
    path = tmp_path / "bars.csv"
    # Has open/high/low/close (so _looks_like_bars says yes) but no column
    # matching any recognized timestamp alias.
    pd.DataFrame({
        "open": [1, 2], "high": [1.5, 2.5], "low": [0.5, 1.5], "close": [1.2, 2.2], "volume": [10, 20],
    }).to_csv(path, index=False)

    with pytest.raises(ValueError, match="timestamp column"):
        load_bars(str(path))


def test_load_bars_drops_rows_with_nan_ohlc(tmp_path):
    # A real outage this project hit: a data source (Yahoo Finance) wrote a
    # blank close for one date in an otherwise-fine bar-level CSV. Loading
    # it silently would poison run_backtest's cumulative equity sum for
    # every bar from that point on (equity is built via `+=`), corrupting
    # the whole backtest rather than just the one bad bar - the same
    # protection ticks_to_bars already gives the resampling path.
    path = tmp_path / "bars.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-05", periods=4, freq="1min"),
        "open": [1, 2, None, 4], "high": [1.5, 2.5, 3.5, 4.5],
        "low": [0.5, 1.5, 2.5, 3.5], "close": [1.2, 2.2, 3.2, 4.2],
        "volume": [10, 20, 30, 40],
    }).to_csv(path, index=False)

    bars = load_bars(str(path))
    assert len(bars) == 3
    assert not bars["open"].isna().any()


def test_load_bars_defaults_missing_volume_to_zero(tmp_path):
    path = tmp_path / "bars.csv"
    # A real shape this project has hit: some historical exports have OHLC
    # but no volume column at all - load_bars must fill it in rather than
    # raising, since volume is the one OHLCV field that isn't required.
    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-05", periods=3, freq="1min"),
        "open": [1, 2, 3], "high": [1.5, 2.5, 3.5], "low": [0.5, 1.5, 2.5], "close": [1.2, 2.2, 3.2],
    }).to_csv(path, index=False)

    bars = load_bars(str(path))
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert (bars["volume"] == 0.0).all()
