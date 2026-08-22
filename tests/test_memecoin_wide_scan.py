import json
import sys

sys.path.insert(0, ".")

import scripts.rug_watch as rug_watch
from scripts.memecoin_wide_scan import _update_rug_watch_history


def _row(symbol, change_24h_pct, pct_from_24h_high=0):
    return {"symbol": symbol, "change_24h_pct": change_24h_pct, "pct_from_24h_high": pct_from_24h_high}


def test_history_appends_and_records_only_flagged_symbols(tmp_path, monkeypatch):
    history_path = tmp_path / "rug_watch_history.json"
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(history_path))

    rows = [_row("CRASHED", -40), _row("FINE", 2)]
    history = _update_rug_watch_history(rows, "2026-08-10T00:00:00Z")

    assert len(history) == 1
    assert history[0]["flagged"] == {"CRASHED": "severe"}
    with open(history_path) as f:
        on_disk = json.load(f)
    assert on_disk["runs"] == history


def test_history_caps_to_max_entries(tmp_path, monkeypatch):
    history_path = tmp_path / "rug_watch_history.json"
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(history_path))
    monkeypatch.setattr(rug_watch, "HISTORY_MAX_ENTRIES", 3)

    for i in range(5):
        history = _update_rug_watch_history([_row("A", -40)], f"run-{i}")

    assert len(history) == 3
    # Oldest runs should have fallen off the front, newest kept.
    assert [r["timestamp"] for r in history] == ["run-2", "run-3", "run-4"]


def test_history_survives_a_corrupt_existing_file(tmp_path, monkeypatch):
    history_path = tmp_path / "rug_watch_history.json"
    history_path.write_text("not valid json{{{")
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(history_path))

    history = _update_rug_watch_history([_row("A", -40)], "2026-08-10T00:00:00Z")
    assert len(history) == 1


def test_main_ranks_movers_flags_thin_liquidity_and_writes_output(tmp_path, monkeypatch):
    import scripts.memecoin_wide_scan as memecoin_wide_scan

    tickers_path = tmp_path / "tickers.json"
    output_path = tmp_path / "wide_scan.json"
    history_path = tmp_path / "rug_watch_history.json"
    monkeypatch.setattr(memecoin_wide_scan, "TICKERS_PATH", str(tickers_path))
    monkeypatch.setattr(memecoin_wide_scan, "OUTPUT_PATH", str(output_path))
    monkeypatch.setattr(rug_watch, "HISTORY_PATH", str(history_path))

    tickers_path.write_text(json.dumps({"symbols": {
        # Up on the day, sitting right at its 24h high - top of the ranked list.
        "PUMP_USD": {"last": 1.0, "high": 1.0, "low": 0.8, "change": 0.30, "volume_value": 500_000, "timestamp": "t1"},
        # Up on the day but with thin liquidity - still ranked, flagged separately.
        "THIN_USD": {"last": 2.0, "high": 2.5, "low": 1.5, "change": 0.05, "volume_value": 1_000, "timestamp": "t1"},
        # Down on the day - lands in not_moving, not ranked.
        "DUMP_USD": {"last": 0.5, "high": 1.0, "low": 0.4, "change": -0.50, "volume_value": 100_000, "timestamp": "t1"},
    }}))

    memecoin_wide_scan.main()

    with open(output_path) as f:
        out = json.load(f)

    assert out["universe_size"] == 3
    assert [r["symbol"] for r in out["ranked"]] == ["PUMP_USD", "THIN_USD"]
    assert out["ranked"][0]["rank"] == 1
    assert out["ranked"][1]["thin_liquidity"] is True
    assert out["ranked"][0]["thin_liquidity"] is False
    assert [r["symbol"] for r in out["not_moving"]] == ["DUMP_USD"]

    # DUMP_USD's -50% change and -50% pct_from_24h_high both clear the
    # severe rug-watch threshold, so main() should have logged it via the
    # already-tested _update_rug_watch_history path.
    with open(history_path) as f:
        history = json.load(f)
    assert history["runs"][-1]["flagged"] == {"DUMP_USD": "severe"}
