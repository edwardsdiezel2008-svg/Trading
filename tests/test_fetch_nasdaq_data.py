import sys

sys.path.insert(0, ".")

from scripts.fetch_nasdaq_data import parse_stooq_csv


def test_parse_stooq_csv_standard_format():
    text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-08-07,578.12,581.44,576.90,580.33,32145600\n"
        "2026-08-08,580.50,584.20,579.10,582.75,29876500\n"
    )
    candles = parse_stooq_csv(text)
    assert len(candles) == 2
    assert candles[0] == {
        "timestamp": "2026-08-07", "open": 578.12, "high": 581.44,
        "low": 576.90, "close": 580.33, "volume": 32145600.0,
    }
    assert candles[1]["timestamp"] == "2026-08-08"


def test_parse_stooq_csv_is_case_insensitive_on_headers():
    text = "date,open,high,low,close,volume\n2026-08-07,1,2,0.5,1.5,100\n"
    candles = parse_stooq_csv(text)
    assert len(candles) == 1
    assert candles[0]["close"] == 1.5


def test_parse_stooq_csv_skips_rows_missing_required_fields():
    text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-08-07,578.12,581.44,576.90,580.33,32145600\n"
        "2026-08-08,,,,\n"  # malformed row - missing OHLC values
    )
    candles = parse_stooq_csv(text)
    assert len(candles) == 1
    assert candles[0]["timestamp"] == "2026-08-07"


def test_parse_stooq_csv_defaults_missing_volume_to_zero():
    text = "Date,Open,High,Low,Close\n2026-08-07,1,2,0.5,1.5\n"
    candles = parse_stooq_csv(text)
    assert len(candles) == 1
    assert candles[0]["volume"] == 0.0


def test_parse_stooq_csv_empty_body_returns_no_candles():
    text = "Date,Open,High,Low,Close,Volume\n"
    assert parse_stooq_csv(text) == []
