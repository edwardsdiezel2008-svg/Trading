import sys

sys.path.insert(0, ".")

import scripts.list_all_tickers as list_all_tickers


def test_main_filters_to_usd_and_usdt_quoted_symbols_and_reports_counts(monkeypatch, capsys):
    tickers = [
        {"i": "BTC_USDT"}, {"i": "ETH_USD"}, {"i": "DOGE_EUR"}, {"i": "SOL_USDT"},
    ]
    monkeypatch.setattr(list_all_tickers, "fetch_tickers", lambda: tickers)

    list_all_tickers.main()

    out = capsys.readouterr().out
    assert "Total instruments: 4" in out
    assert "USD/USDT-quoted: 3" in out
    assert "BTC_USDT" in out
    assert "ETH_USD" in out
    assert "SOL_USDT" in out
    assert "DOGE_EUR" not in out


def test_main_deduplicates_and_sorts_symbols(monkeypatch, capsys):
    tickers = [{"i": "SOL_USD"}, {"i": "BTC_USD"}, {"i": "BTC_USD"}]
    monkeypatch.setattr(list_all_tickers, "fetch_tickers", lambda: tickers)

    list_all_tickers.main()

    out = capsys.readouterr().out
    assert "Total instruments: 2" in out
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines.index("BTC_USD") < lines.index("SOL_USD")
