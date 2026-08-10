import sys

sys.path.insert(0, ".")

import pandas as pd

from scripts.fetch_index_futures import INDEX_FUTURES, _df_to_candles


def _make_df(rows, tz=None):
    idx = pd.to_datetime([r[0] for r in rows])
    if tz:
        idx = idx.tz_localize(tz)
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=idx,
    )


def test_df_to_candles_basic():
    df = _make_df([("2026-08-01", 24000.0, 24100.0, 23950.0, 24050.0, 12345.0)])
    candles = _df_to_candles(df)
    assert len(candles) == 1
    c = candles[0]
    assert c["open"] == 24000.0
    assert c["high"] == 24100.0
    assert c["low"] == 23950.0
    assert c["close"] == 24050.0
    assert c["volume"] == 12345.0
    assert c["timestamp"].startswith("2026-08-01")


def test_df_to_candles_converts_tz_aware_to_naive_utc():
    df = _make_df([("2026-08-01 09:30", 100.0, 101.0, 99.0, 100.5, 10.0)], tz="America/New_York")
    candles = _df_to_candles(df)
    # 09:30 ET during EDT is 13:30 UTC
    assert candles[0]["timestamp"] == "2026-08-01T13:30:00"


def test_df_to_candles_nan_volume_defaults_to_zero():
    df = _make_df([("2026-08-01", 100.0, 101.0, 99.0, 100.5, float("nan"))])
    candles = _df_to_candles(df)
    assert candles[0]["volume"] == 0.0


def test_df_to_candles_multiple_rows_preserve_order():
    df = _make_df([
        ("2026-08-01", 100.0, 101.0, 99.0, 100.5, 10.0),
        ("2026-08-02", 101.0, 102.0, 100.0, 101.5, 20.0),
    ])
    candles = _df_to_candles(df)
    assert len(candles) == 2
    assert candles[0]["timestamp"] < candles[1]["timestamp"]


def test_df_to_candles_empty_df():
    df = _make_df([])
    assert _df_to_candles(df) == []


def test_index_futures_config_has_distinct_paths_per_symbol():
    symbols = [row[0] for row in INDEX_FUTURES]
    daily_paths = [row[1] for row in INDEX_FUTURES]
    five_min_paths = [row[2] for row in INDEX_FUTURES]
    assert len(symbols) == len(set(symbols)), "duplicate Yahoo symbol"
    assert len(daily_paths) == len(set(daily_paths)), "daily bars path collision"
    assert len(five_min_paths) == len(set(five_min_paths)), "5-minute bars path collision"
    assert "NQ=F" in symbols and "ES=F" in symbols and "YM=F" in symbols and "GC=F" in symbols
