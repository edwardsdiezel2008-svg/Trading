import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from scripts.paper_trade_update import (
    _load_funding_rate,
    accrue_funding,
    liquidation_price,
    perp_max_loss_fraction,
)


def test_perp_max_loss_fraction_at_typical_leverage():
    assert perp_max_loss_fraction(3.0) == 1.0 - 3.0 * 0.005


def test_perp_max_loss_fraction_clamps_to_zero_at_extreme_leverage():
    # 1 - leverage*0.005 would go negative past 200x - clamp instead of
    # returning a nonsensical negative loss fraction.
    assert perp_max_loss_fraction(250.0) == 0.0


def test_liquidation_price_none_when_flat():
    assert liquidation_price(100.0, 0, 3.0, 0.985) is None


def test_liquidation_price_none_when_unleveraged():
    assert liquidation_price(100.0, 1, 1.0, 0.995) is None


def test_liquidation_price_below_entry_for_a_long():
    price = liquidation_price(100.0, 1, 3.0, 0.985)
    assert price == 100.0 * (1 - 0.985 / 3.0)
    assert price < 100.0


def test_liquidation_price_above_entry_for_a_short():
    price = liquidation_price(100.0, -1, 3.0, 0.985)
    assert price == 100.0 * (1 + 0.985 / 3.0)
    assert price > 100.0


def test_accrue_funding_first_call_establishes_baseline_without_backdating():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    accrued, ts, applied = accrue_funding(0.0, None, now, direction=1, notional=300_000, funding_rate=0.0001)
    assert accrued == 0.0
    assert ts == now
    assert applied is True


def test_accrue_funding_skips_reapplication_within_the_guard_window():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)
    accrued, ts, applied = accrue_funding(10.0, t0, t1, direction=1, notional=300_000, funding_rate=0.0001, min_interval_minutes=30)
    assert accrued == 10.0
    assert ts == t0
    assert applied is False


def test_accrue_funding_long_pays_when_rate_is_positive():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    accrued, ts, applied = accrue_funding(0.0, t0, t1, direction=1, notional=300_000, funding_rate=0.0001)
    assert applied is True
    assert ts == t1
    assert accrued == -300_000 * 0.0001  # cost to the long


def test_accrue_funding_short_receives_when_rate_is_positive():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    accrued, ts, applied = accrue_funding(0.0, t0, t1, direction=-1, notional=300_000, funding_rate=0.0001)
    assert accrued == 300_000 * 0.0001  # credit to the short


def test_accrue_funding_flat_position_advances_timestamp_with_no_delta():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    accrued, ts, applied = accrue_funding(5.0, t0, t1, direction=0, notional=0, funding_rate=0.0001)
    assert accrued == 5.0
    assert ts == t1
    assert applied is True


def test_accrue_funding_missing_rate_applies_no_delta():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    accrued, ts, applied = accrue_funding(5.0, t0, t1, direction=1, notional=300_000, funding_rate=None)
    assert accrued == 5.0
    assert applied is True


def test_load_funding_rate_missing_file_returns_none(tmp_path):
    assert _load_funding_rate(str(tmp_path / "missing.json")) is None


def test_load_funding_rate_parses_the_nested_rate_string(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"funding_rate": {"rate": "0.0001119", "timestamp": "t", "instrument_name": "BTCUSD-PERP"}}))
    assert _load_funding_rate(str(path)) == 0.0001119


def test_load_funding_rate_missing_key_returns_none(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"order_book": {}}))
    assert _load_funding_rate(str(path)) is None


def test_load_funding_rate_malformed_json_returns_none(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("{not valid json")
    assert _load_funding_rate(str(path)) is None
