import csv
import os
import sys

sys.path.insert(0, ".")

from scripts.fetch_market_data import (
    _candle_timestamp,
    _first,
    _normalize_book_level,
    _normalize_instrument,
    _normalize_ticker,
    _sanitize_ohlc,
    _ticker_symbol,
    merge_bars_csv,
)


def test_normalize_instrument_inserts_underscore_before_the_quote_currency():
    assert _normalize_instrument("DOGEUSD") == "DOGE_USD"
    assert _normalize_instrument("BTCUSDT") == "BTC_USDT"


def test_normalize_instrument_leaves_already_underscored_symbols_alone():
    assert _normalize_instrument("BTC_USDT") == "BTC_USDT"


def test_normalize_instrument_leaves_unrecognized_suffixes_alone():
    assert _normalize_instrument("WEIRDPAIR") == "WEIRDPAIR"


def test_first_returns_the_first_present_and_non_none_key():
    assert _first({"a": None, "b": 5, "c": 10}, "a", "b", "c") == 5


def test_first_falls_back_to_default_when_nothing_matches():
    assert _first({}, "a", "b", default="x") == "x"


def test_ticker_symbol_checks_every_known_key_alias():
    assert _ticker_symbol({"i": "BTC_USDT"}) == "BTC_USDT"
    assert _ticker_symbol({"instrument_name": "ETH_USDT"}) == "ETH_USDT"


def test_ticker_symbol_raises_a_descriptive_error_when_no_alias_matches():
    try:
        _ticker_symbol({"unrelated_key": "x"})
        assert False, "expected KeyError"
    except KeyError as e:
        assert "unrelated_key" in str(e)


def test_normalize_ticker_handles_short_key_shape_with_epoch_ms_timestamp():
    raw = {"a": "50000.5", "h": "51000", "l": "49000", "c": "1.5", "vv": "1000000", "t": 1_700_000_000_000}
    out = _normalize_ticker(raw)
    assert out["last"] == "50000.5"
    assert out["high"] == "51000"
    assert out["low"] == "49000"
    assert out["change"] == "1.5"
    assert out["volume_value"] == "1000000"
    assert out["timestamp"] == "2023-11-14T22:13:20Z"


def test_normalize_ticker_handles_long_key_shape_with_iso_timestamp():
    raw = {"last": "100", "high": "110", "low": "90", "change": "0.5", "volume_value": "500", "timestamp": "2026-01-01T00:00:00Z"}
    out = _normalize_ticker(raw)
    assert out["last"] == "100"
    assert out["timestamp"] == "2026-01-01T00:00:00Z"


def test_normalize_ticker_defaults_missing_fields_to_zero_string():
    out = _normalize_ticker({})
    assert out == {"last": "0", "high": "0", "low": "0", "change": "0", "volume_value": "0", "timestamp": ""}


def test_normalize_book_level_handles_list_shape():
    assert _normalize_book_level([50000, 1.25, 3]) == ["50000", "1.25"]


def test_normalize_book_level_handles_list_shape_missing_size():
    assert _normalize_book_level([50000]) == ["50000", "0"]


def test_normalize_book_level_handles_dict_shape_with_short_keys():
    assert _normalize_book_level({"p": 50000, "q": 1.25}) == ["50000", "1.25"]


def test_normalize_book_level_handles_dict_shape_with_long_keys():
    assert _normalize_book_level({"price": 50000, "quantity": 1.25}) == ["50000", "1.25"]


def test_normalize_book_level_handles_a_bare_scalar():
    assert _normalize_book_level(50000) == ["50000", "0"]


def test_candle_timestamp_handles_epoch_ms_shape():
    dt = _candle_timestamp({"t": 1_700_000_000_000})
    assert dt.isoformat() == "2023-11-14T22:13:20"


def test_candle_timestamp_handles_iso_string_shape():
    dt = _candle_timestamp({"timestamp": "2026-01-01T12:00:00Z"})
    assert dt.isoformat() == "2026-01-01T12:00:00"


def test_sanitize_ohlc_leaves_a_sane_candle_untouched():
    o, h, l, cl = _sanitize_ohlc(100, 110, 95, 105)
    assert (o, h, l, cl) == (100.0, 110.0, 95.0, 105.0)


def test_sanitize_ohlc_clamps_a_zero_low_to_the_lesser_of_open_and_close():
    # A real bug this project hit in deep historical data: low=0 is not a
    # real price, and left alone it fakes a near-100% true-range spike that
    # blows up ATR-based strategies reading that bar.
    o, h, l, cl = _sanitize_ohlc(100, 110, 0, 105)
    assert l == 100.0  # min(open, close)


def test_sanitize_ohlc_clamps_a_low_above_open_and_close_too():
    o, h, l, cl = _sanitize_ohlc(100, 110, 108, 105)
    assert l == 100.0


def test_sanitize_ohlc_passes_through_unparseable_values_unchanged():
    assert _sanitize_ohlc("bad", 110, 95, 105) == ("bad", 110, 95, 105)


def test_merge_bars_csv_writes_new_rows_sorted_by_timestamp(tmp_path):
    path = str(tmp_path / "bars.csv")
    candles = [
        {"t": 1_700_000_000_000, "o": 2, "h": 3, "l": 1, "c": 2.5, "v": 10},
        {"t": 1_699_900_000_000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 5},
    ]
    n = merge_bars_csv(path, candles)
    assert n == 2
    with open(path) as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["timestamp", "open", "high", "low", "close", "volume"]
    # Earlier timestamp (1_699_900_000_000) must sort first.
    assert rows[1][0] < rows[2][0]


def test_merge_bars_csv_overwrites_a_row_for_the_same_timestamp_instead_of_duplicating(tmp_path):
    path = str(tmp_path / "bars.csv")
    merge_bars_csv(path, [{"t": 1_700_000_000_000, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}])
    n = merge_bars_csv(path, [{"t": 1_700_000_000_000, "o": 9, "h": 9, "l": 9, "c": 9, "v": 9}])
    assert n == 1
    with open(path) as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2  # header + one data row
    assert rows[1][1] == "9.0"  # updated open, not the stale value


def test_merge_bars_csv_preserves_existing_rows_not_present_in_the_new_batch(tmp_path):
    path = str(tmp_path / "bars.csv")
    merge_bars_csv(path, [{"t": 1_699_900_000_000, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}])
    n = merge_bars_csv(path, [{"t": 1_700_000_000_000, "o": 2, "h": 2, "l": 2, "c": 2, "v": 2}])
    assert n == 2
    with open(path) as f:
        rows = list(csv.reader(f))
    assert len(rows) == 3  # header + two data rows, the older one kept


def test_merge_bars_csv_skips_a_candle_with_unparseable_ohlc_instead_of_writing_it(tmp_path):
    # A real outage this project hit: a blank/unparseable field from the
    # upstream source (Yahoo Finance) passed through _sanitize_ohlc
    # unchanged and got written straight into the CSV - load_bars then
    # loaded that garbage silently, poisoning run_backtest's cumulative
    # equity sum for every bar afterward and crashing the site build
    # downstream. A missing bar (skip it) is far cheaper than a bad one
    # baked permanently into the historical record.
    path = str(tmp_path / "bars.csv")
    candles = [
        {"t": 1_700_000_000_000, "o": "", "h": 3, "l": 1, "c": 2.5, "v": 10},
        {"t": 1_699_900_000_000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 5},
    ]
    n = merge_bars_csv(path, candles)
    assert n == 1
    with open(path) as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2  # header + only the one good row
    assert rows[1][1] == "1.0"


def test_merge_bars_csv_skips_a_candle_with_nan_ohlc(tmp_path):
    path = str(tmp_path / "bars.csv")
    n = merge_bars_csv(path, [{"t": 1_700_000_000_000, "o": float("nan"), "h": 3, "l": 1, "c": 2.5, "v": 10}])
    assert n == 0


def test_merge_bars_csv_date_only_mode_collapses_intraday_candles_onto_one_daily_row(tmp_path):
    path = str(tmp_path / "bars.csv")
    candles = [
        {"timestamp": "2026-01-01T00:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1},
        {"timestamp": "2026-01-01T12:00:00Z", "o": 2, "h": 2, "l": 2, "c": 2, "v": 2},
    ]
    n = merge_bars_csv(path, candles, date_only=True)
    assert n == 1
    with open(path) as f:
        rows = list(csv.reader(f))
    assert rows[1][0] == "2026-01-01"
    assert rows[1][1] == "2.0"  # the later same-day candle wins


def test_get_returns_the_result_payload_on_success(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    class FakeResponse:
        ok = True
        status_code = 200
        url = "https://api.crypto.com/exchange/v1/public/get-tickers"
        text = ""

        def json(self):
            return {"code": 0, "result": {"data": ["ok"]}}

    monkeypatch.setattr(fetch_market_data.requests, "get", lambda url, params, timeout: FakeResponse())

    assert fetch_market_data._get("get-tickers") == {"data": ["ok"]}


def test_get_retries_on_a_transient_error_then_succeeds(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    calls = []

    class FakeResponse:
        ok = True
        status_code = 200
        url = "https://api.crypto.com/exchange/v1/public/get-tickers"
        text = ""

        def json(self):
            return {"code": 0, "result": {"data": []}}

    def fake_get(url, params, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise ConnectionError("temporary network blip")
        return FakeResponse()

    monkeypatch.setattr(fetch_market_data.requests, "get", fake_get)
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    result = fetch_market_data._get("get-tickers", retries=3)

    assert len(calls) == 3
    assert result == {"data": []}


def test_get_raises_after_exhausting_all_retries(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    def fake_get(url, params, timeout):
        raise ConnectionError("exchange is unreachable")

    monkeypatch.setattr(fetch_market_data.requests, "get", fake_get)
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    try:
        fetch_market_data._get("get-tickers", retries=3)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "get-tickers" in str(e)
        assert "after 3 attempts" in str(e)


def test_get_raises_on_a_non_ok_http_status_with_body_text_included(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    class FakeResponse:
        ok = False
        status_code = 404
        url = "https://api.crypto.com/exchange/v1/public/get-tickers"
        text = "instrument not found"

        def json(self):
            raise AssertionError("should not be called when resp.ok is False")

    monkeypatch.setattr(fetch_market_data.requests, "get", lambda url, params, timeout: FakeResponse())
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    try:
        fetch_market_data._get("get-tickers", retries=1)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "404" in str(e)
        assert "instrument not found" in str(e)


def test_get_raises_when_the_api_body_reports_a_nonzero_error_code(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    class FakeResponse:
        ok = True
        status_code = 200
        url = "https://api.crypto.com/exchange/v1/public/get-tickers"
        text = ""

        def json(self):
            return {"code": 10004, "message": "INVALID_REQUEST"}

    monkeypatch.setattr(fetch_market_data.requests, "get", lambda url, params, timeout: FakeResponse())
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    try:
        fetch_market_data._get("get-tickers", retries=1)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "10004" in str(e)


def test_fetch_candlestick_paginated_stops_when_a_page_adds_no_new_candles(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    def make_candle(ts_ms):
        return {"t": ts_ms, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}

    # Page 1: three candles at t=3000,2000,1000. Page 2: the API doesn't
    # really support end_ts pagination here and just returns the same latest
    # page again - the "no new candles" guard should stop after that repeat
    # rather than looping forever.
    page1 = [make_candle(3000), make_candle(2000), make_candle(1000)]
    calls = []

    def fake_get(path, params=None):
        calls.append(dict(params or {}))
        return {"data": page1}

    monkeypatch.setattr(fetch_market_data, "_get", fake_get)
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    candles = fetch_market_data.fetch_candlestick_paginated("BTCUSD", "1h", max_candles=100, page_size=3)

    assert len(candles) == 3
    assert len(calls) == 2  # one real page, one repeat that triggers the stop guard
    assert calls[0]["instrument_name"] == "BTC_USD"


def test_fetch_candlestick_paginated_stops_once_max_candles_is_reached(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    def make_candle(ts_ms):
        return {"t": ts_ms, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}

    # Each page is strictly older than the last, so pagination could in
    # principle continue forever - max_candles must be what stops it.
    pages = [
        [make_candle(30000), make_candle(20000)],
        [make_candle(10000), make_candle(0)],
        [make_candle(-10000), make_candle(-20000)],
    ]
    call_count = [0]

    def fake_get(path, params=None):
        page = pages[call_count[0]]
        call_count[0] += 1
        return {"data": page}

    monkeypatch.setattr(fetch_market_data, "_get", fake_get)
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    candles = fetch_market_data.fetch_candlestick_paginated("BTCUSD", "1h", max_candles=4, page_size=2)

    assert len(candles) >= 4
    assert call_count[0] == 2  # stopped as soon as max_candles was reached


def test_fetch_tickers_returns_the_data_list(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.setattr(fetch_market_data, "_get", lambda path: {"data": [{"i": "BTC_USD"}]})

    assert fetch_market_data.fetch_tickers() == [{"i": "BTC_USD"}]


def test_fetch_candlestick_returns_the_data_list_and_normalizes_the_instrument(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    seen_params = {}

    def fake_get(path, params):
        seen_params.update(params)
        return {"data": ["candle1"]}

    monkeypatch.setattr(fetch_market_data, "_get", fake_get)

    result = fetch_market_data.fetch_candlestick("DOGEUSD", "1h", count=50)

    assert result == ["candle1"]
    assert seen_params == {"instrument_name": "DOGE_USD", "timeframe": "1h", "count": 50}


def _fake_candle(t=1_700_000_000_000, c=100.0):
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": 1.0}


def test_backfill_daily_history_writes_every_target_via_pagination(tmp_path, monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [("ETH_USDT", "paper_trading/bars_eth.csv")])

    def fake_paginated(symbol, timeframe, max_candles):
        return [_fake_candle(t=1_700_000_000_000 + i * 86_400_000) for i in range(3)]

    monkeypatch.setattr(fetch_market_data, "fetch_candlestick_paginated", fake_paginated)

    fetch_market_data.backfill_daily_history(max_candles=100)

    assert os.path.exists("paper_trading/bars.csv")
    assert os.path.exists("paper_trading/bars_eth.csv")
    with open("paper_trading/bars.csv") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 4  # header + 3 candles


def test_backfill_daily_history_warns_and_continues_past_a_failing_symbol(tmp_path, monkeypatch, capsys):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [("ETH_USDT", "paper_trading/bars_eth.csv")])

    def fake_paginated(symbol, timeframe, max_candles):
        if symbol == fetch_market_data.BTC_SYMBOL:
            raise RuntimeError("exchange unreachable")
        return [_fake_candle()]

    monkeypatch.setattr(fetch_market_data, "fetch_candlestick_paginated", fake_paginated)

    fetch_market_data.backfill_daily_history(max_candles=100)

    out = capsys.readouterr().out
    assert "WARN: backfill failed for BTC_USDT" in out
    assert not os.path.exists("paper_trading/bars.csv")
    assert os.path.exists("paper_trading/bars_eth.csv")  # the other target still ran


def test_main_writes_every_output_file_end_to_end(tmp_path, monkeypatch):
    import json

    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [("ETH_USDT", "paper_trading/bars_eth.csv")])
    monkeypatch.setattr(fetch_market_data, "MEME_PRECISE_SYMBOLS", ["DOGEUSD"])
    monkeypatch.setattr(fetch_market_data, "MEME_WIDE_SYMBOLS", ["DOGEUSD"])
    monkeypatch.setattr(fetch_market_data, "fetch_candlestick", lambda symbol, timeframe, count=300: [_fake_candle()])
    monkeypatch.setattr(fetch_market_data, "fetch_tickers", lambda: [{"i": "DOGE_USD", "a": "0.1", "b": "0.2", "c": "0.15", "v": "1000", "h": "0.2", "l": "0.1", "t": 1_700_000_000_000}])
    monkeypatch.setattr(fetch_market_data, "fetch_order_book", lambda symbol: {"bids": [["1", "2"]], "asks": [["3", "4"]], "timestamp": "t"})
    monkeypatch.setattr(fetch_market_data, "fetch_funding_rate", lambda instrument_name=None, count=1: {"rate": "0.0001", "timestamp": "t", "instrument_name": instrument_name})
    monkeypatch.setattr(fetch_market_data, "fetch_fear_greed", lambda: {"value": 50, "classification": "Neutral", "timestamp": "t"})

    fetch_market_data.main()

    assert os.path.exists("paper_trading/bars.csv")
    assert os.path.exists("paper_trading/bars_15m.csv")
    assert os.path.exists("paper_trading/bars_eth.csv")
    assert os.path.exists("paper_trading/memecoins/DOGEUSD.csv")

    with open("paper_trading/memecoins_wide_tickers.json") as f:
        wide = json.load(f)
    assert "DOGEUSD" in wide["symbols"]

    with open("paper_trading/btc_market_snapshot.json") as f:
        snapshot = json.load(f)
    assert snapshot["order_book"]["bids"] == [["1", "2"]]
    assert snapshot["funding_rate"]["rate"] == "0.0001"

    with open("paper_trading/eth_market_snapshot.json") as f:
        eth_snapshot = json.load(f)
    assert eth_snapshot["funding_rate"]["rate"] == "0.0001"

    with open("paper_trading/fear_greed.json") as f:
        fng = json.load(f)
    assert fng["value"] == 50


def test_main_omits_market_snapshot_when_book_and_funding_both_fail(tmp_path, monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [])
    monkeypatch.setattr(fetch_market_data, "MEME_PRECISE_SYMBOLS", [])
    monkeypatch.setattr(fetch_market_data, "MEME_WIDE_SYMBOLS", [])
    monkeypatch.setattr(fetch_market_data, "fetch_candlestick", lambda symbol, timeframe, count=300: [_fake_candle()])
    monkeypatch.setattr(fetch_market_data, "fetch_tickers", lambda: [])

    def raise_error(*args, **kwargs):
        raise RuntimeError("exchange unreachable")

    monkeypatch.setattr(fetch_market_data, "fetch_order_book", raise_error)
    monkeypatch.setattr(fetch_market_data, "fetch_funding_rate", raise_error)
    monkeypatch.setattr(fetch_market_data, "fetch_fear_greed", raise_error)

    fetch_market_data.main()  # must not raise despite every optional fetch failing

    assert not os.path.exists("paper_trading/btc_market_snapshot.json")
    assert not os.path.exists("paper_trading/eth_market_snapshot.json")
    assert not os.path.exists("paper_trading/fear_greed.json")
    # The core bars still got written even though every optional extra failed.
    assert os.path.exists("paper_trading/bars.csv")


def test_main_skips_a_failing_memecoin_and_continues_with_the_rest(tmp_path, monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [])
    monkeypatch.setattr(fetch_market_data, "MEME_PRECISE_SYMBOLS", ["BROKENUSD", "OKUSD"])
    monkeypatch.setattr(fetch_market_data, "MEME_WIDE_SYMBOLS", [])
    monkeypatch.setattr(fetch_market_data, "fetch_tickers", lambda: [])
    monkeypatch.setattr(fetch_market_data, "fetch_order_book", lambda symbol: {"bids": [], "asks": [], "timestamp": "t"})
    monkeypatch.setattr(fetch_market_data, "fetch_funding_rate", lambda instrument_name=None, count=1: None)
    monkeypatch.setattr(fetch_market_data, "fetch_fear_greed", lambda: None)

    def fake_candlestick(symbol, timeframe, count=300):
        if symbol == "BROKENUSD" and timeframe == "1h":
            raise RuntimeError("this coin's feed is down")
        return [_fake_candle()]

    monkeypatch.setattr(fetch_market_data, "fetch_candlestick", fake_candlestick)

    fetch_market_data.main()  # BROKENUSD's failure must not stop OKUSD from being written

    assert not os.path.exists("paper_trading/memecoins/BROKENUSD.csv")
    assert os.path.exists("paper_trading/memecoins/OKUSD.csv")


def test_fetch_order_book_handles_the_data_wrapped_shape(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.setattr(fetch_market_data, "_get", lambda path, params: {
        "depth": 10,
        "data": [{"bids": [["100", "1"]], "asks": [["101", "2"]], "t": 1_700_000_000_000}],
    })

    book = fetch_market_data.fetch_order_book("BTC_USD")

    assert book["bids"] == [["100", "1"]]
    assert book["asks"] == [["101", "2"]]
    assert book["timestamp"].startswith("2023-11-14")


def test_fetch_order_book_handles_the_flat_top_level_shape(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.setattr(fetch_market_data, "_get", lambda path, params: {
        "bids": [["100", "1"]], "asks": [["101", "2"]],
    })

    book = fetch_market_data.fetch_order_book("BTC_USD")

    assert book["bids"] == [["100", "1"]]
    assert book["asks"] == [["101", "2"]]
    assert book["timestamp"] == ""


def test_fetch_funding_rate_returns_the_latest_entry(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    seen = {}

    def fake_get(path, params, base_url=None):
        seen["base_url"] = base_url
        return {"data": [{"v": "0.0001", "t": 1_700_000_000_000}]}

    monkeypatch.setattr(fetch_market_data, "_get", fake_get)

    rate = fetch_market_data.fetch_funding_rate("BTCUSD-PERP")

    assert rate["rate"] == "0.0001"
    assert rate["instrument_name"] == "BTCUSD-PERP"
    assert rate["timestamp"].startswith("2023-11-14")
    assert seen["base_url"] == fetch_market_data.DERIV_BASE_URL


def test_fetch_funding_rate_returns_none_when_there_is_no_data(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.setattr(fetch_market_data, "_get", lambda path, params, base_url=None: {"data": []})

    assert fetch_market_data.fetch_funding_rate("BTCUSD-PERP") is None


def test_fetch_fear_greed_parses_the_latest_entry(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"value": "34", "value_classification": "Fear", "timestamp": "1700000000"}]}

    monkeypatch.setattr(fetch_market_data.requests, "get", lambda url, params, timeout: FakeResponse())

    fng = fetch_market_data.fetch_fear_greed()

    assert fng["value"] == 34
    assert fng["classification"] == "Fear"
    assert fng["timestamp"].startswith("2023-11-14")


def test_fetch_fear_greed_returns_none_when_there_is_no_data(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": []}

    monkeypatch.setattr(fetch_market_data.requests, "get", lambda url, params, timeout: FakeResponse())

    assert fetch_market_data.fetch_fear_greed() is None


def test_fetch_fear_greed_tolerates_an_unparseable_timestamp(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"value": "50", "value_classification": "Neutral", "timestamp": "not-a-number"}]}

    monkeypatch.setattr(fetch_market_data.requests, "get", lambda url, params, timeout: FakeResponse())

    fng = fetch_market_data.fetch_fear_greed()

    assert fng["value"] == 50
    assert fng["timestamp"] == "not-a-number"  # left as-is when it can't be parsed as an epoch


def test_fetch_candlestick_paginated_stops_on_a_completely_empty_page(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    def make_candle(ts_ms):
        return {"t": ts_ms, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}

    # History genuinely runs out: page 1 has real candles, page 2 comes back
    # with an empty data list rather than repeating page 1 or returning fewer
    # candles than requested.
    pages = [[make_candle(3000), make_candle(2000)], []]
    call_count = [0]

    def fake_get(path, params=None):
        page = pages[call_count[0]]
        call_count[0] += 1
        return {"data": page}

    monkeypatch.setattr(fetch_market_data, "_get", fake_get)
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    candles = fetch_market_data.fetch_candlestick_paginated("BTCUSD", "1h", max_candles=100, page_size=2)

    assert len(candles) == 2
    assert call_count[0] == 2


def test_fetch_candlestick_paginated_stops_when_a_page_is_smaller_than_requested(monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    def make_candle(ts_ms):
        return {"t": ts_ms, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}

    # The exchange has fewer candles left than a full page_size - a real
    # signal that history is exhausted, distinct from an outright empty page.
    pages = [[make_candle(3000), make_candle(2000), make_candle(1000)], [make_candle(500)]]
    call_count = [0]

    def fake_get(path, params=None):
        page = pages[call_count[0]]
        call_count[0] += 1
        return {"data": page}

    monkeypatch.setattr(fetch_market_data, "_get", fake_get)
    monkeypatch.setattr(fetch_market_data.time, "sleep", lambda seconds: None)

    candles = fetch_market_data.fetch_candlestick_paginated("BTCUSD", "1h", max_candles=100, page_size=3)

    assert len(candles) == 4  # both pages' candles kept
    assert call_count[0] == 2  # stopped after the short page, no third request


def test_main_continues_past_an_other_instrument_daily_fetch_failure(tmp_path, monkeypatch):
    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [
        ("ETH_USDT", "paper_trading/bars_eth.csv"), ("SOL_USDT", "paper_trading/bars_sol.csv"),
    ])
    monkeypatch.setattr(fetch_market_data, "MEME_PRECISE_SYMBOLS", [])
    monkeypatch.setattr(fetch_market_data, "MEME_WIDE_SYMBOLS", [])
    monkeypatch.setattr(fetch_market_data, "fetch_tickers", lambda: [])
    monkeypatch.setattr(fetch_market_data, "fetch_order_book", lambda symbol: {"bids": [], "asks": [], "timestamp": "t"})
    monkeypatch.setattr(fetch_market_data, "fetch_funding_rate", lambda instrument_name=None, count=1: None)
    monkeypatch.setattr(fetch_market_data, "fetch_fear_greed", lambda: None)

    def flaky_fetch(symbol, timeframe, count=300):
        if symbol == "ETH_USDT" and timeframe == "1D":
            raise RuntimeError("ETH_USDT daily fetch is unreachable")
        return [_fake_candle()]

    monkeypatch.setattr(fetch_market_data, "fetch_candlestick", flaky_fetch)

    fetch_market_data.main()  # ETH_USDT's failure must not stop SOL_USDT or crash the run

    assert not os.path.exists("paper_trading/bars_eth.csv")
    assert os.path.exists("paper_trading/bars_sol.csv")


def test_main_warns_but_continues_when_a_wide_scan_symbol_is_missing_from_tickers(tmp_path, monkeypatch):
    import json

    import scripts.fetch_market_data as fetch_market_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fetch_market_data, "OTHER_INSTRUMENTS", [])
    monkeypatch.setattr(fetch_market_data, "MEME_PRECISE_SYMBOLS", [])
    monkeypatch.setattr(fetch_market_data, "MEME_WIDE_SYMBOLS", ["FOUNDUSD", "MISSINGUSD"])
    monkeypatch.setattr(fetch_market_data, "fetch_candlestick", lambda symbol, timeframe, count=300: [_fake_candle()])
    # Only FOUNDUSD's ticker actually comes back - MISSINGUSD is a real gap
    # some symbols hit (delisted, mistyped, or simply absent from this run's
    # snapshot) and main() must report it rather than crashing or silently
    # fabricating an entry.
    monkeypatch.setattr(fetch_market_data, "fetch_tickers", lambda: [
        {"i": "FOUND_USD", "a": "0.1", "b": "0.2", "c": "0.15", "v": "1000", "h": "0.2", "l": "0.1", "t": 1_700_000_000_000},
    ])
    monkeypatch.setattr(fetch_market_data, "fetch_order_book", lambda symbol: {"bids": [], "asks": [], "timestamp": "t"})
    monkeypatch.setattr(fetch_market_data, "fetch_funding_rate", lambda instrument_name=None, count=1: None)
    monkeypatch.setattr(fetch_market_data, "fetch_fear_greed", lambda: None)

    fetch_market_data.main()  # must not raise despite the missing symbol

    with open("paper_trading/memecoins_wide_tickers.json") as f:
        wide = json.load(f)
    assert "FOUNDUSD" in wide["symbols"]
    assert "MISSINGUSD" not in wide["symbols"]
