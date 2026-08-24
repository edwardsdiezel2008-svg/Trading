import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, ".")

from scripts.fetch_alpaca_data import _fetch_crypto_bars, _fetch_stock_bars, main, parse_args


def _multi_symbol_df(symbols):
    rows = []
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    for symbol in symbols:
        for i, ts in enumerate(idx):
            rows.append({
                "symbol": symbol, "timestamp": ts,
                "open": 1.0 + i, "high": 1.5 + i, "low": 0.5 + i, "close": 1.2 + i, "volume": 100 + i,
            })
    df = pd.DataFrame(rows).set_index(["symbol", "timestamp"])
    return df


def test_parse_args_applies_defaults():
    args = parse_args(["--symbols", "AAPL", "MSFT", "--start", "2026-01-01", "--end", "2026-02-01"])
    assert args.asset_class == "stock"
    assert args.timeframe == "1Min"
    assert args.feed == "iex"
    assert args.output_dir == "data/raw"


def test_fetch_stock_bars_raises_systemexit_when_credentials_are_missing(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    args = parse_args(["--symbols", "AAPL", "--start", "2026-01-01", "--end", "2026-02-01"])

    with pytest.raises(SystemExit, match="Missing credentials"):
        _fetch_stock_bars(args)


class _FakeBarsResponse:
    def __init__(self, df):
        self.df = df


def test_fetch_stock_bars_builds_the_request_and_returns_the_client_s_dataframe(monkeypatch):
    import alpaca.data.historical as adh

    captured = {}

    class FakeStockClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def get_stock_bars(self, request):
            captured["request"] = request
            return _FakeBarsResponse(_multi_symbol_df(["AAPL"]))

    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    monkeypatch.setattr(adh, "StockHistoricalDataClient", FakeStockClient)

    args = parse_args(["--symbols", "AAPL", "--start", "2026-01-01", "--end", "2026-01-03", "--feed", "sip"])
    df = _fetch_stock_bars(args)

    assert captured["client_kwargs"] == {"api_key": "test-key", "secret_key": "test-secret"}
    assert captured["request"].symbol_or_symbols == ["AAPL"]
    assert df.equals(_multi_symbol_df(["AAPL"]))


def test_fetch_crypto_bars_needs_no_credentials_and_returns_the_client_s_dataframe(monkeypatch):
    import alpaca.data.historical as adh

    captured = {}

    class FakeCryptoClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def get_crypto_bars(self, request):
            captured["request"] = request
            return _FakeBarsResponse(_multi_symbol_df(["BTC/USD"]))

    monkeypatch.setattr(adh, "CryptoHistoricalDataClient", FakeCryptoClient)

    args = parse_args(["--asset-class", "crypto", "--symbols", "BTC/USD", "--start", "2026-01-01", "--end", "2026-01-03"])
    df = _fetch_crypto_bars(args)

    assert captured["client_kwargs"] == {}
    assert captured["request"].symbol_or_symbols == ["BTC/USD"]
    assert df.equals(_multi_symbol_df(["BTC/USD"]))


def test_main_writes_a_csv_per_symbol_with_slash_safe_filenames(tmp_path, monkeypatch):
    import scripts.fetch_alpaca_data as fetch_alpaca_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_alpaca_data, "_fetch_crypto_bars", lambda args: _multi_symbol_df(["BTC/USD", "ETH/USD"]))

    main(["--asset-class", "crypto", "--symbols", "BTC/USD", "ETH/USD",
          "--start", "2026-01-01", "--end", "2026-01-03", "--timeframe", "1Day"])

    assert os.path.exists("data/raw/BTC-USD_1Day_bars.csv")
    assert os.path.exists("data/raw/ETH-USD_1Day_bars.csv")

    written = pd.read_csv("data/raw/BTC-USD_1Day_bars.csv")
    assert list(written.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(written) == 2


def test_main_skips_a_requested_symbol_missing_from_the_response(tmp_path, monkeypatch):
    import scripts.fetch_alpaca_data as fetch_alpaca_data

    monkeypatch.chdir(tmp_path)
    # Only AAPL comes back, even though MSFT was requested too - e.g. a
    # delisted or mistyped symbol Alpaca silently drops rather than erroring.
    monkeypatch.setattr(fetch_alpaca_data, "_fetch_stock_bars", lambda args: _multi_symbol_df(["AAPL"]))

    main(["--symbols", "AAPL", "MSFT", "--start", "2026-01-01", "--end", "2026-01-03", "--timeframe", "1Day"])

    assert os.path.exists("data/raw/AAPL_1Day_bars.csv")
    assert not os.path.exists("data/raw/MSFT_1Day_bars.csv")


def test_main_raises_systemexit_when_no_bars_are_returned_at_all(tmp_path, monkeypatch):
    import scripts.fetch_alpaca_data as fetch_alpaca_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_alpaca_data, "_fetch_stock_bars", lambda args: pd.DataFrame())

    with pytest.raises(SystemExit, match="No bars returned"):
        main(["--symbols", "NOSUCHTICKER", "--start", "2026-01-01", "--end", "2026-01-03"])


def test_main_wraps_an_underlying_request_failure_in_a_systemexit(tmp_path, monkeypatch):
    import scripts.fetch_alpaca_data as fetch_alpaca_data

    monkeypatch.chdir(tmp_path)

    def raise_error(args):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(fetch_alpaca_data, "_fetch_stock_bars", raise_error)

    with pytest.raises(SystemExit, match="Request to Alpaca failed"):
        main(["--symbols", "AAPL", "--start", "2026-01-01", "--end", "2026-01-03"])
