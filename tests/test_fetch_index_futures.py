import sys

sys.path.insert(0, ".")

import pandas as pd

from scripts.fetch_index_futures import INDEX_FUTURES, NQ_EXTRA_INTERVALS, _df_to_candles


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
    assert "RTY=F" in symbols and "CL=F" in symbols


def test_nq_extra_intervals_has_distinct_intervals_and_paths():
    intervals = [row[0] for row in NQ_EXTRA_INTERVALS]
    paths = [row[2] for row in NQ_EXTRA_INTERVALS]
    assert len(intervals) == len(set(intervals)), "duplicate interval"
    assert len(paths) == len(set(paths)), "output path collision"
    assert set(intervals) == {"1m", "15m", "1h"}
    assert all(p.startswith("paper_trading/bars_nq") for p in paths)
    # None of these paths may collide with the existing daily/5-min NQ files.
    existing_nq_paths = {row[1] for row in INDEX_FUTURES if row[0] == "NQ=F"} | {
        row[2] for row in INDEX_FUTURES if row[0] == "NQ=F"
    }
    assert not (set(paths) & existing_nq_paths)


def test_fetch_history_retries_on_empty_response_then_succeeds(monkeypatch):
    import yfinance as yf

    import scripts.fetch_index_futures as fetch_index_futures

    good_df = _make_df([("2026-08-01", 100.0, 101.0, 99.0, 100.5, 10.0)])
    calls = []

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period, interval, auto_adjust):
            calls.append(1)
            return pd.DataFrame() if len(calls) < 3 else good_df

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    monkeypatch.setattr(fetch_index_futures.time, "sleep", lambda seconds: None)

    df = fetch_index_futures._fetch_history("NQ=F", period="10y", interval="1d", retries=3)

    assert len(calls) == 3
    assert not df.empty


def test_fetch_history_retries_on_an_exception_then_succeeds(monkeypatch):
    import yfinance as yf

    import scripts.fetch_index_futures as fetch_index_futures

    good_df = _make_df([("2026-08-01", 100.0, 101.0, 99.0, 100.5, 10.0)])
    calls = []

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period, interval, auto_adjust):
            calls.append(1)
            if len(calls) < 2:
                raise ConnectionError("temporary network blip")
            return good_df

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    monkeypatch.setattr(fetch_index_futures.time, "sleep", lambda seconds: None)

    df = fetch_index_futures._fetch_history("NQ=F", period="10y", interval="1d", retries=3)

    assert len(calls) == 2
    assert not df.empty


def test_fetch_history_raises_after_exhausting_all_retries(monkeypatch):
    import yfinance as yf

    import scripts.fetch_index_futures as fetch_index_futures

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period, interval, auto_adjust):
            raise ConnectionError("Yahoo is unreachable")

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    monkeypatch.setattr(fetch_index_futures.time, "sleep", lambda seconds: None)

    try:
        fetch_index_futures._fetch_history("NQ=F", period="10y", interval="1d", retries=3)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "NQ=F" in str(e)
        assert "after 3 attempts" in str(e)


def test_main_writes_every_symbol_and_interval_when_all_fetches_succeed(monkeypatch):
    import scripts.fetch_index_futures as fetch_index_futures

    fake_df = _make_df([("2026-08-01", 100.0, 101.0, 99.0, 100.5, 10.0)])
    merged_paths = []

    monkeypatch.setattr(fetch_index_futures, "_fetch_history", lambda symbol, period, interval, retries=3: fake_df)
    monkeypatch.setattr(fetch_index_futures, "merge_bars_csv", lambda path, candles, date_only: merged_paths.append(path) or 1)

    fetch_index_futures.main()  # should not raise

    expected = {row[1] for row in INDEX_FUTURES} | {row[2] for row in INDEX_FUTURES} | {row[2] for row in NQ_EXTRA_INTERVALS}
    assert set(merged_paths) == expected


def test_main_raises_systemexit_when_every_fetch_fails(monkeypatch):
    import scripts.fetch_index_futures as fetch_index_futures

    def always_fails(symbol, period, interval, retries=3):
        raise RuntimeError("Yahoo is unreachable")

    monkeypatch.setattr(fetch_index_futures, "_fetch_history", always_fails)

    try:
        fetch_index_futures.main()
        assert False, "expected a SystemExit"
    except SystemExit as e:
        assert "failed" in str(e)


def test_main_continues_past_a_single_symbols_failure(monkeypatch):
    import scripts.fetch_index_futures as fetch_index_futures

    fake_df = _make_df([("2026-08-01", 100.0, 101.0, 99.0, 100.5, 10.0)])
    merged_paths = []

    def flaky_fetch(symbol, period, interval, retries=3):
        if symbol == "ES=F":
            raise RuntimeError("ES=F is unreachable")
        return fake_df

    monkeypatch.setattr(fetch_index_futures, "_fetch_history", flaky_fetch)
    monkeypatch.setattr(fetch_index_futures, "merge_bars_csv", lambda path, candles, date_only: merged_paths.append(path) or 1)

    fetch_index_futures.main()  # ES=F fails, but others should still write - no SystemExit

    assert "paper_trading/bars_es.csv" not in merged_paths
    assert "paper_trading/bars_nq.csv" in merged_paths
