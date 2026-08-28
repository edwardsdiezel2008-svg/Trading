import sys
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, ".")

from scripts.paper_trade_update import (
    _buy_and_hold_curve,
    _downsample_equity_curve,
    _update_track_record,
)


def test_downsample_equity_curve_keeps_every_point_under_the_limit():
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    curve = pd.Series([100.0, 101.234, 99.5, 102.0, 103.456], index=idx)
    out = _downsample_equity_curve(idx, curve, max_points=250)
    assert out == [
        [str(idx[0]), 100.0],
        [str(idx[1]), 101.23],
        [str(idx[2]), 99.5],
        [str(idx[3]), 102.0],
        [str(idx[4]), 103.46],
    ]


def test_downsample_equity_curve_always_keeps_first_and_last_point():
    idx = pd.date_range("2026-01-01", periods=1000, freq="min")
    curve = pd.Series(range(1000), dtype=float, index=idx)
    out = _downsample_equity_curve(idx, curve, max_points=250)
    assert out[0] == [str(idx[0]), 0.0]
    assert out[-1] == [str(idx[999]), 999.0]
    assert len(out) <= 250
    # Downsampled points must stay in original chronological order.
    assert [row[0] for row in out] == sorted(row[0] for row in out)


def test_buy_and_hold_curve_scales_capital_by_price_return():
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    bars = pd.DataFrame({"close": [100.0, 150.0, 50.0]}, index=idx)
    curve = _buy_and_hold_curve(bars, capital=1000.0)
    assert list(curve) == [1000.0, 1500.0, 500.0]


def test_buy_and_hold_curve_falls_back_to_flat_capital_when_first_price_is_zero():
    # A zero first close would divide-by-zero the return calc - must not
    # crash or return NaN/inf, just hold capital flat instead.
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    bars = pd.DataFrame({"close": [0.0, 150.0, 50.0]}, index=idx)
    curve = _buy_and_hold_curve(bars, capital=1000.0)
    assert list(curve) == [1000.0, 1000.0, 1000.0]


def _result(equity_values, positions_values, index):
    return SimpleNamespace(
        equity_curve=pd.Series(equity_values, index=index),
        positions=pd.Series(positions_values, index=index),
    )


def test_update_track_record_computes_return_since_the_tracking_start_bar(tmp_path):
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    bars = pd.DataFrame({"close": [1.0] * 5}, index=idx)
    # Tracking starts at the 3rd bar (idx[2]) - equity_at_start must be the
    # bar *before* it (idx[1] = 100), not the tracking-start bar itself.
    result = _result([100.0, 100.0, 110.0, 120.0, 130.0], [1, 1, 1, 1, 1], idx)
    path = tmp_path / "track_record.csv"
    _update_track_record(bars, "Trend", result, capital=100_000.0, tracking_start=idx[2], track_record_path=str(path))

    df = pd.read_csv(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["strategy"] == "Trend"
    assert row["equity"] == 130.0
    assert row["return_since_tracking_start_pct"] == pytest.approx((130.0 / 100.0 - 1) * 100, abs=1e-6)


def test_update_track_record_falls_back_to_capital_when_tracking_start_predates_history(tmp_path):
    idx = pd.date_range("2026-01-10", periods=3, freq="D")
    bars = pd.DataFrame({"close": [1.0] * 3}, index=idx)
    result = _result([120.0, 150.0, 200.0], [1, 1, 1], idx)
    path = tmp_path / "track_record.csv"
    # tracking_start is earlier than every bar in this history - must not
    # crash on the missing index lookup, and must measure return against
    # starting capital rather than an out-of-range prior bar.
    _update_track_record(
        bars, "Trend", result, capital=100_000.0,
        tracking_start=pd.Timestamp("2020-01-01"), track_record_path=str(path),
    )
    df = pd.read_csv(path)
    assert df.iloc[0]["return_since_tracking_start_pct"] == pytest.approx((200.0 / 100_000.0 - 1) * 100, abs=1e-6)


def test_update_track_record_shows_zero_not_a_sign_flip_when_start_equity_is_already_negative(tmp_path):
    # A max_loss_fraction floor is only checked at bar close, so a large
    # enough gap can still push equity non-positive (confirmed reachable on
    # real futures data - see engine.py's max_loss_fraction docstring). If
    # the bar right before tracking_start already has negative equity and
    # the account loses even MORE by the latest bar, dividing a more-negative
    # current_equity by a negative equity_at_start can produce a ratio > 1 -
    # i.e. a POSITIVE displayed return for an account that actually lost
    # more money. Must show 0%, not a sign-flipped percentage, whichever
    # direction equity moves from there.
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    bars = pd.DataFrame({"close": [1.0] * 3}, index=idx)
    result = _result([100.0, -1000.0, -1200.0], [1, 1, 1], idx)
    path = tmp_path / "track_record.csv"
    _update_track_record(bars, "Trend", result, capital=100_000.0, tracking_start=idx[2], track_record_path=str(path))

    df = pd.read_csv(path)
    assert df.iloc[0]["equity"] == -1200.0
    assert df.iloc[0]["return_since_tracking_start_pct"] == 0.0


def test_update_track_record_replaces_rather_than_duplicates_the_same_date_and_strategy(tmp_path):
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    bars = pd.DataFrame({"close": [1.0, 1.0]}, index=idx)
    path = tmp_path / "track_record.csv"

    result1 = _result([100.0, 105.0], [1, 1], idx)
    _update_track_record(bars, "Trend", result1, capital=100.0, tracking_start=idx[0], track_record_path=str(path))
    # Re-running the same latest bar (e.g. a re-triggered workflow) must
    # overwrite that row, not append a second one for the same date+strategy.
    result2 = _result([100.0, 107.0], [1, 1], idx)
    _update_track_record(bars, "Trend", result2, capital=100.0, tracking_start=idx[0], track_record_path=str(path))

    df = pd.read_csv(path)
    assert len(df) == 1
    assert df.iloc[0]["equity"] == 107.0


def test_update_track_record_keeps_rows_for_other_strategies_and_dates(tmp_path):
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    bars = pd.DataFrame({"close": [1.0, 1.0]}, index=idx)
    path = tmp_path / "track_record.csv"

    result_a = _result([100.0, 105.0], [1, 1], idx)
    _update_track_record(bars, "Trend", result_a, capital=100.0, tracking_start=idx[0], track_record_path=str(path))
    result_b = _result([100.0, 95.0], [-1, -1], idx)
    _update_track_record(bars, "MeanReversion", result_b, capital=100.0, tracking_start=idx[0], track_record_path=str(path))

    df = pd.read_csv(path)
    assert len(df) == 2
    assert set(df["strategy"]) == {"Trend", "MeanReversion"}
