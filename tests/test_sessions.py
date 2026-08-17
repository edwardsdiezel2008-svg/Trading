from datetime import datetime
from zoneinfo import ZoneInfo

from src.backtest.sessions import (
    ALBERTA_TZ,
    SESSIONS,
    cme_session_status,
    convert,
    session_status,
    to_alberta,
)


def _utc(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=ZoneInfo("UTC"))


def test_convert_naive_time_to_alberta():
    ny_open = datetime(2025, 6, 10, 9, 30)  # summer -> MDT (UTC-6), NY is EDT (UTC-4)
    alberta = convert(ny_open, "America/New_York")
    assert alberta.tzinfo is not None
    assert (alberta.hour, alberta.minute) == (7, 30)


def test_convert_handles_dst_independently_per_zone():
    # Jan: Alberta is MST (UTC-7), Tokyo has no DST (UTC+9) -> 16h offset,
    # so 09:00 Tokyo lands at 17:00 the previous day in Alberta.
    tokyo_open = datetime(2025, 1, 15, 9, 0)
    alberta = convert(tokyo_open, "Asia/Tokyo")
    assert (alberta.day, alberta.hour, alberta.minute) == (14, 17, 0)


def test_to_alberta_requires_aware_datetime():
    try:
        to_alberta(datetime(2025, 1, 1, 0, 0))
        assert False, "expected ValueError for naive datetime"
    except ValueError:
        pass


def test_new_york_session_open_and_closed():
    ny_session = next(s for s in SESSIONS if s.name.startswith("New York (NYSE"))
    # 2025-06-10 is a Tuesday. NYSE 9:30-16:00 ET = 13:30-20:00 UTC in summer (EDT).
    open_status = session_status(ny_session, _utc(2025, 6, 10, 15, 0))
    assert open_status["is_open"] is True
    assert open_status["next_event"] == "closes"

    closed_status = session_status(ny_session, _utc(2025, 6, 10, 21, 0))
    assert closed_status["is_open"] is False
    assert closed_status["next_event"] == "opens"
    # Next open should be the next trading day (Wednesday).
    assert closed_status["next_event_time"].date().isoformat() == "2025-06-11"


def test_session_status_skips_weekends():
    ny_session = next(s for s in SESSIONS if s.name.startswith("New York (NYSE"))
    # 2025-06-14 is a Saturday.
    status = session_status(ny_session, _utc(2025, 6, 14, 15, 0))
    assert status["is_open"] is False
    # Next open must be Monday, not Sunday.
    assert status["next_event_time"].strftime("%A") == "Monday"


def test_cme_daily_halt():
    # Tuesday 2025-06-10, 16:30 CT = 21:30 UTC (CDT, UTC-5) -> inside the halt.
    status = cme_session_status(_utc(2025, 6, 10, 21, 30))
    assert status["is_open"] is False
    assert status["next_event_time"].time().isoformat(timespec="minutes") == "17:00"


def test_cme_open_during_normal_hours():
    # Tuesday 2025-06-10, 12:00 CT = 17:00 UTC -> open, halts at 16:00 CT.
    status = cme_session_status(_utc(2025, 6, 10, 17, 0))
    assert status["is_open"] is True
    assert status["next_event"] == "halts"


def test_cme_closed_saturday_opens_sunday():
    # Saturday 2025-06-14, noon CT.
    status = cme_session_status(_utc(2025, 6, 14, 17, 0))
    assert status["is_open"] is False
    assert status["next_event_time"].strftime("%A %H:%M") == "Sunday 17:00"


def test_cme_closed_friday_evening_until_sunday():
    # Friday 2025-06-13, 20:00 CT (after the 16:00 CT weekly close).
    status = cme_session_status(_utc(2025, 6, 14, 1, 0))
    assert status["is_open"] is False
    assert status["next_event_time"].strftime("%A %H:%M") == "Sunday 17:00"


def test_all_status_times_are_alberta_tz():
    from src.backtest.sessions import all_sessions_status

    rows = all_sessions_status(_utc(2025, 6, 10, 15, 0))
    assert len(rows) == len(SESSIONS) + 1  # + CME
    for row in rows:
        assert row["next_event_time_alberta"].tzinfo.key == ALBERTA_TZ.key
