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
