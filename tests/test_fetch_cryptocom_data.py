import sys

import pandas as pd
import pytest

sys.path.insert(0, ".")

import scripts.fetch_cryptocom_data as fetch_cryptocom_data


class _FakeResponse:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise fetch_cryptocom_data.requests.exceptions.HTTPError("bad status")

    def json(self):
        return self._payload


def _candle(t_ms, o, h, l, c, v):
    return {"t": t_ms, "o": o, "h": h, "l": l, "c": c, "v": v}


def test_parse_args_applies_defaults():
    args = fetch_cryptocom_data.parse_args([])
    assert args.instrument == "BTC_USDT"
    assert args.timeframe == "1D"
    assert args.count == 300
    assert args.output_dir == "data/raw"


def test_main_writes_a_csv_of_the_returned_candles(tmp_path, monkeypatch):
    candles = [
        _candle(1_700_000_000_000, 100.0, 105.0, 95.0, 102.0, 10.0),
        _candle(1_700_086_400_000, 102.0, 110.0, 101.0, 108.0, 20.0),
    ]
    payload = {"code": 0, "result": {"data": candles}}

    def fake_get(url, params, timeout):
        assert url == fetch_cryptocom_data.API_URL
        assert params["instrument_name"] == "BTC_USDT"
        return _FakeResponse(payload)

    monkeypatch.setattr(fetch_cryptocom_data.requests, "get", fake_get)

    fetch_cryptocom_data.main(["--instrument", "BTC_USDT", "--timeframe", "1D", "--count", "2", "--output-dir", str(tmp_path)])

    out_path = tmp_path / "BTC_USDT_1D_bars.csv"
    assert out_path.exists()
    df = pd.read_csv(out_path)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df.iloc[0]["close"] == 102.0


def test_main_raises_systemexit_when_the_request_itself_fails(tmp_path, monkeypatch):
    def fake_get(url, params, timeout):
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(fetch_cryptocom_data.requests, "get", fake_get)

    with pytest.raises(SystemExit, match="Request to Crypto.com failed"):
        fetch_cryptocom_data.main(["--output-dir", str(tmp_path)])


def test_main_raises_systemexit_on_a_bad_http_status(tmp_path, monkeypatch):
    def fake_get(url, params, timeout):
        return _FakeResponse({}, status_ok=False)

    monkeypatch.setattr(fetch_cryptocom_data.requests, "get", fake_get)

    with pytest.raises(SystemExit, match="Request to Crypto.com failed"):
        fetch_cryptocom_data.main(["--output-dir", str(tmp_path)])


def test_main_raises_systemexit_when_the_api_reports_a_nonzero_error_code(tmp_path, monkeypatch):
    payload = {"code": 10004, "message": "bad param"}

    def fake_get(url, params, timeout):
        return _FakeResponse(payload)

    monkeypatch.setattr(fetch_cryptocom_data.requests, "get", fake_get)

    with pytest.raises(SystemExit, match="error payload"):
        fetch_cryptocom_data.main(["--output-dir", str(tmp_path)])


def test_main_raises_systemexit_when_the_response_shape_is_unexpected(tmp_path, monkeypatch):
    payload = {"code": 0, "result": {"not_data": []}}

    def fake_get(url, params, timeout):
        return _FakeResponse(payload)

    monkeypatch.setattr(fetch_cryptocom_data.requests, "get", fake_get)

    with pytest.raises(SystemExit, match="Unexpected response shape"):
        fetch_cryptocom_data.main(["--output-dir", str(tmp_path)])


def test_main_raises_systemexit_when_no_candles_are_returned(tmp_path, monkeypatch):
    payload = {"code": 0, "result": {"data": []}}

    def fake_get(url, params, timeout):
        return _FakeResponse(payload)

    monkeypatch.setattr(fetch_cryptocom_data.requests, "get", fake_get)

    with pytest.raises(SystemExit, match="No candles returned"):
        fetch_cryptocom_data.main(["--output-dir", str(tmp_path)])
