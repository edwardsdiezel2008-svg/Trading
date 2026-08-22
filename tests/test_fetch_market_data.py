import csv
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
