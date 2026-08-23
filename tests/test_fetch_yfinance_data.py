import os
import sys

import pandas as pd

sys.path.insert(0, ".")

from scripts.fetch_yfinance_data import _fetch_one, main, parse_args


def _daily_df():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", name="Date")
    return pd.DataFrame({
        "Open": [1.0, 2.0, 3.0], "High": [1.5, 2.5, 3.5], "Low": [0.5, 1.5, 2.5],
        "Close": [1.2, 2.2, 3.2], "Volume": [100, 200, 300],
    }, index=idx)


def _intraday_df():
    idx = pd.date_range("2026-01-01 09:30", periods=3, freq="1min", name="Datetime")
    return pd.DataFrame({
        "Open": [1.0, 2.0, 3.0], "High": [1.5, 2.5, 3.5], "Low": [0.5, 1.5, 2.5],
        "Close": [1.2, 2.2, 3.2], "Volume": [100, 200, 300],
    }, index=idx)


def test_parse_args_applies_defaults():
    args = parse_args(["--symbols", "AAPL", "MSFT", "--start", "2026-01-01", "--end", "2026-02-01"])
    assert args.symbols == ["AAPL", "MSFT"]
    assert args.interval == "1d"
    assert args.output_dir == "data/raw"


def test_fetch_one_renames_the_date_column_for_daily_bars(monkeypatch):
    import scripts.fetch_yfinance_data as fetch_yfinance_data

    monkeypatch.setattr(fetch_yfinance_data.yf, "download", lambda *a, **k: _daily_df())

    df = _fetch_one("AAPL", "2026-01-01", "2026-01-04", "1d")

    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["close"].tolist() == [1.2, 2.2, 3.2]


def test_fetch_one_renames_the_datetime_column_for_intraday_bars(monkeypatch):
    import scripts.fetch_yfinance_data as fetch_yfinance_data

    monkeypatch.setattr(fetch_yfinance_data.yf, "download", lambda *a, **k: _intraday_df())

    df = _fetch_one("AAPL", "2026-01-01", "2026-01-02", "1m")

    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3


def test_fetch_one_collapses_a_multiindex_column_shape(monkeypatch):
    import scripts.fetch_yfinance_data as fetch_yfinance_data

    df = _daily_df()
    df.columns = pd.MultiIndex.from_product([df.columns, ["AAPL"]])
    monkeypatch.setattr(fetch_yfinance_data.yf, "download", lambda *a, **k: df)

    out = _fetch_one("AAPL", "2026-01-01", "2026-01-04", "1d")

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(out) == 3


def test_fetch_one_returns_an_empty_dataframe_when_yfinance_returns_none(monkeypatch):
    import scripts.fetch_yfinance_data as fetch_yfinance_data

    monkeypatch.setattr(fetch_yfinance_data.yf, "download", lambda *a, **k: None)

    assert _fetch_one("NOSUCHTICKER", "2026-01-01", "2026-01-04", "1d").empty


def test_fetch_one_returns_an_empty_dataframe_when_yfinance_returns_an_empty_frame(monkeypatch):
    import scripts.fetch_yfinance_data as fetch_yfinance_data

    monkeypatch.setattr(fetch_yfinance_data.yf, "download", lambda *a, **k: pd.DataFrame())

    assert _fetch_one("NOSUCHTICKER", "2026-01-01", "2026-01-04", "1d").empty


def test_main_writes_a_csv_per_successful_symbol_and_skips_failures(tmp_path, monkeypatch):
    import scripts.fetch_yfinance_data as fetch_yfinance_data

    monkeypatch.chdir(tmp_path)

    def fake_fetch_one(symbol, start, end, interval):
        if symbol == "BROKEN":
            raise RuntimeError("no data for BROKEN")
        if symbol == "EMPTY":
            return pd.DataFrame()
        return pd.DataFrame({
            "timestamp": ["2026-01-01"], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [100],
        })

    monkeypatch.setattr(fetch_yfinance_data, "_fetch_one", fake_fetch_one)

    main(["--symbols", "AAPL", "BROKEN", "EMPTY", "--start", "2026-01-01", "--end", "2026-01-02", "--output-dir", "data/raw"])

    assert os.path.exists("data/raw/AAPL_1d_bars.csv")
    assert not os.path.exists("data/raw/BROKEN_1d_bars.csv")
    assert not os.path.exists("data/raw/EMPTY_1d_bars.csv")
