"""Trading session times for major global markets, centralized and converted
to Alberta time (America/Edmonton).

Alberta observes the same DST rules as the rest of North America (Mountain
Time: MST = UTC-7 in winter, MDT = UTC-6 in summer). `zoneinfo` handles the
DST transitions for every market automatically - no manual offset math.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ALBERTA_TZ = ZoneInfo("America/Edmonton")
UTC = ZoneInfo("UTC")

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
WEEKDAYS = (MON, TUE, WED, THU, FRI)


@dataclass(frozen=True)
class MarketSession:
    name: str
    asset_class: str  # "equity" or "forex"
    tz_name: str
    open_time: time
    close_time: time
    weekdays: tuple = WEEKDAYS  # which local weekdays the session opens on

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


# Regular trading hours, local exchange time. Equities close same-day
# (open_time < close_time), so no overnight wraparound to model.
SESSIONS = [
    MarketSession("Sydney (ASX)", "equity", "Australia/Sydney", time(10, 0), time(16, 0)),
    MarketSession("Tokyo (TSE)", "equity", "Asia/Tokyo", time(9, 0), time(15, 0)),
    MarketSession("Hong Kong (HKEX)", "equity", "Asia/Hong_Kong", time(9, 30), time(16, 0)),
    MarketSession("Shanghai (SSE)", "equity", "Asia/Shanghai", time(9, 30), time(15, 0)),
    MarketSession("Singapore (SGX)", "equity", "Asia/Singapore", time(9, 0), time(17, 0)),
    MarketSession("Frankfurt (Xetra)", "equity", "Europe/Berlin", time(9, 0), time(17, 30)),
    MarketSession("London (LSE)", "equity", "Europe/London", time(8, 0), time(16, 30)),
    MarketSession("New York (NYSE/NASDAQ)", "equity", "America/New_York", time(9, 30), time(16, 0)),
    # Classic 4-city forex trading sessions (local conventions).
    MarketSession("Sydney FX", "forex", "Australia/Sydney", time(7, 0), time(16, 0)),
    MarketSession("Tokyo FX", "forex", "Asia/Tokyo", time(9, 0), time(18, 0)),
    MarketSession("London FX", "forex", "Europe/London", time(8, 0), time(17, 0)),
    MarketSession("New York FX", "forex", "America/New_York", time(8, 0), time(17, 0)),
]

# CME Globex (ES, MES, NQ, MNQ, YM, RTY, CL, GC, ...): nearly 24h, Sunday
# 17:00 CT through Friday 16:00 CT, with a daily maintenance halt 16:00-17:00
# CT Sun-Thu. This shape (weekend closed + daily halt) doesn't fit the
# single daily open/close window the regular sessions use, so it gets its
# own rule-based status function instead of a MarketSession entry.
CME_NAME = "CME Globex (ES/NQ/CL/GC futures)"
CME_TZ = ZoneInfo("America/Chicago")
CME_HALT_START = time(16, 0)
CME_HALT_END = time(17, 0)


def to_alberta(dt: datetime) -> datetime:
    """Convert an aware datetime to Alberta time (America/Edmonton)."""
    if dt.tzinfo is None:
        raise ValueError("dt must be timezone-aware; use convert() for naive local times")
    return dt.astimezone(ALBERTA_TZ)


def convert(dt: datetime, from_tz: str) -> datetime:
    """Convert `dt` into Alberta time.

    If `dt` is naive, it's treated as a wall-clock time in `from_tz`. If it's
    already timezone-aware, `from_tz` is ignored and it's just re-expressed
    in Alberta time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(from_tz))
    return dt.astimezone(ALBERTA_TZ)


def _combine(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def _next_weekday(d: date, weekday: int) -> date:
    days_ahead = (weekday - d.weekday()) % 7
    days_ahead = days_ahead or 7
    return d + timedelta(days=days_ahead)


def session_status(session: MarketSession, now_utc: datetime | None = None) -> dict:
    """Is `session` open right now, and when's the next open/close?

    Returns a dict with is_open, next_event ("opens"/"closes"), and
    next_event_time (aware datetime in the session's local tz).
    """
    now_utc = now_utc or datetime.now(UTC)
    tz = session.tz
    now_local = now_utc.astimezone(tz)
    today = now_local.date()

    windows = [
        (_combine(today + timedelta(days=delta), session.open_time, tz),
         _combine(today + timedelta(days=delta), session.close_time, tz))
        for delta in range(-1, 9)
        if (today + timedelta(days=delta)).weekday() in session.weekdays
    ]

    for opens, closes in windows:
        if opens <= now_local < closes:
            return {"is_open": True, "next_event": "closes", "next_event_time": closes}

    next_open = min((o for o, c in windows if o > now_local), default=None)
    return {"is_open": False, "next_event": "opens", "next_event_time": next_open}


def cme_session_status(now_utc: datetime | None = None) -> dict:
    """Same shape as session_status(), for CME Globex's Sun-Fri/daily-halt schedule."""
    now_utc = now_utc or datetime.now(UTC)
    now_local = now_utc.astimezone(CME_TZ)
    wd = now_local.weekday()
    t = now_local.time()
    today = now_local.date()

    if wd == SAT:
        next_open = _combine(_next_weekday(today, SUN), CME_HALT_END, CME_TZ)
        return {"is_open": False, "next_event": "opens", "next_event_time": next_open}

    if wd == SUN:
        if t < CME_HALT_END:
            return {"is_open": False, "next_event": "opens",
                     "next_event_time": _combine(today, CME_HALT_END, CME_TZ)}
        return {"is_open": True, "next_event": "halts",
                "next_event_time": _combine(today + timedelta(days=1), CME_HALT_START, CME_TZ)}

    if wd == FRI:
        if t < CME_HALT_START:
            return {"is_open": True, "next_event": "closes for the week",
                     "next_event_time": _combine(today, CME_HALT_START, CME_TZ)}
        next_open = _combine(_next_weekday(today, SUN), CME_HALT_END, CME_TZ)
        return {"is_open": False, "next_event": "opens", "next_event_time": next_open}

    # Mon-Thu
    if t < CME_HALT_START:
        return {"is_open": True, "next_event": "halts",
                "next_event_time": _combine(today, CME_HALT_START, CME_TZ)}
    if t < CME_HALT_END:
        return {"is_open": False, "next_event": "opens",
                "next_event_time": _combine(today, CME_HALT_END, CME_TZ)}
    return {"is_open": True, "next_event": "halts",
            "next_event_time": _combine(today + timedelta(days=1), CME_HALT_START, CME_TZ)}


def all_sessions_status(now_utc: datetime | None = None) -> list[dict]:
    """Status of every session, sorted by how soon the next event happens,
    with next_event_time converted into Alberta time.
    """
    now_utc = now_utc or datetime.now(UTC)
    rows = []
    for session in SESSIONS:
        status = session_status(session, now_utc)
        rows.append({
            "name": session.name,
            "asset_class": session.asset_class,
            "is_open": status["is_open"],
            "next_event": status["next_event"],
            "next_event_time_alberta": to_alberta(status["next_event_time"]),
        })

    cme = cme_session_status(now_utc)
    rows.append({
        "name": CME_NAME,
        "asset_class": "future",
        "is_open": cme["is_open"],
        "next_event": cme["next_event"],
        "next_event_time_alberta": to_alberta(cme["next_event_time"]),
    })

    rows.sort(key=lambda r: r["next_event_time_alberta"])
    return rows
