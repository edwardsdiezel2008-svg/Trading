#!/usr/bin/env python
"""Centralized time calculator - everything converted into Alberta time.

Shows the open/closed status of every major trading session (equities,
forex, CME futures), with every time expressed in Alberta time
(America/Edmonton). Also converts one-off times from any timezone.

Usage:
    python scripts/time_calculator.py
    python scripts/time_calculator.py --convert 14:30 --tz America/New_York
    python scripts/time_calculator.py --convert "2025-03-10 09:30" --tz Europe/London
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.sessions import ALBERTA_TZ, all_sessions_status, convert


def print_board() -> None:
    now_alberta = datetime.now(ALBERTA_TZ)
    print(f"Alberta time (America/Edmonton): {now_alberta:%Y-%m-%d %H:%M %Z}\n")

    rows = all_sessions_status()
    name_width = max(len("Session"), *(len(row["name"]) for row in rows))
    header = f"{'Session':<{name_width}} {'Class':<8} {'Status':<7} Next event (Alberta time)"
    print(header)
    print("-" * len(header))
    for row in rows:
        status = "OPEN" if row["is_open"] else "closed"
        when = row["next_event_time_alberta"].strftime("%a %H:%M")
        print(f"{row['name']:<{name_width}} {row['asset_class']:<8} {status:<7} {row['next_event']} {when}")


def print_conversion(value: str, tz_name: str) -> None:
    if tz_name not in available_timezones():
        print(f"Unknown timezone: {tz_name}", file=sys.stderr)
        sys.exit(1)

    parsed = None
    for fmt in ("%Y-%m-%d %H:%M", "%H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":
            today = datetime.now(ZoneInfo(tz_name)).date()
            parsed = parsed.replace(year=today.year, month=today.month, day=today.day)
        break

    if parsed is None:
        print(f"Could not parse '{value}'. Use 'HH:MM' or 'YYYY-MM-DD HH:MM'.", file=sys.stderr)
        sys.exit(1)

    alberta_time = convert(parsed, tz_name)
    print(f"{value} ({tz_name}) = {alberta_time:%Y-%m-%d %H:%M %Z} in Alberta")


def main() -> None:
    parser = argparse.ArgumentParser(description="Centralized time calculator (Alberta time)")
    parser.add_argument("--convert", metavar="TIME", help="Time to convert, e.g. '14:30' or '2025-03-10 09:30'")
    parser.add_argument("--tz", metavar="ZONE", help="Source timezone, e.g. America/New_York (required with --convert)")
    args = parser.parse_args()

    if args.convert:
        if not args.tz:
            parser.error("--convert requires --tz")
        print_conversion(args.convert, args.tz)
    else:
        print_board()


if __name__ == "__main__":
    main()
