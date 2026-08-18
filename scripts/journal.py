#!/usr/bin/env python3
"""Daily journal: one folder per day of tasks/notes, plus the index the
live calendar planner (journal/calendar.html) reads.

    python scripts/journal.py new                    # scaffold today's folder
    python scripts/journal.py task "wire up the X"    # append a task to today
    python scripts/journal.py task "fix the bug" --done
    python scripts/journal.py note "why we did it this way"
    python scripts/journal.py index                   # rebuild journal/index.json
    python scripts/journal.py serve                    # serve the repo + auto-rebuild the index on change
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_DIR = REPO_ROOT / "journal"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TASK_RE = re.compile(r"^- \[( |x|X)\]\s*(.*)$")


def today_str() -> str:
    return date.today().isoformat()


def day_dir(date_str: str) -> Path:
    if not DATE_RE.match(date_str):
        raise ValueError(f"expected YYYY-MM-DD, got {date_str!r}")
    return JOURNAL_DIR / date_str


def ensure_day(date_str: str) -> Path:
    d = day_dir(date_str)
    d.mkdir(parents=True, exist_ok=True)
    tasks_md = d / "tasks.md"
    notes_md = d / "notes.md"
    if not tasks_md.exists():
        tasks_md.write_text("")
    if not notes_md.exists():
        notes_md.write_text(f"# {date_str}\n\n")
    return d


def add_task(date_str: str, text: str, done: bool = False) -> None:
    d = ensure_day(date_str)
    tasks_md = d / "tasks.md"
    box = "x" if done else " "
    with tasks_md.open("a") as f:
        f.write(f"- [{box}] {text}\n")


def add_note(date_str: str, text: str) -> None:
    d = ensure_day(date_str)
    notes_md = d / "notes.md"
    with notes_md.open("a") as f:
        f.write(f"{text}\n\n")


def parse_tasks(text: str) -> list[dict]:
    tasks = []
    for line in text.splitlines():
        m = TASK_RE.match(line.strip())
        if m:
            tasks.append({"text": m.group(2).strip(), "done": m.group(1).lower() == "x"})
    return tasks


def note_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        return line.lstrip("#").strip()
    return ""


def build_index() -> dict:
    days = {}
    if JOURNAL_DIR.exists():
        for d in sorted(JOURNAL_DIR.iterdir()):
            if not d.is_dir() or not DATE_RE.match(d.name):
                continue
            tasks_md = d / "tasks.md"
            notes_md = d / "notes.md"
            tasks = parse_tasks(tasks_md.read_text()) if tasks_md.exists() else []
            notes_text = notes_md.read_text() if notes_md.exists() else ""
            days[d.name] = {
                "tasks": tasks,
                "task_count": len(tasks),
                "done_count": sum(1 for t in tasks if t["done"]),
                "title": note_title(notes_text),
                "notes": notes_text.strip(),
            }
    index = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "days": days}
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    (JOURNAL_DIR / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def _mtimes() -> dict:
    if not JOURNAL_DIR.exists():
        return {}
    return {
        str(p): p.stat().st_mtime
        for p in JOURNAL_DIR.rglob("*")
        if p.is_file() and p.name != "index.json"
    }


def serve(port: int = 8420) -> None:
    """Serve the repo root and keep journal/index.json rebuilt whenever a
    tasks.md/notes.md file changes, so calendar.html (which polls
    journal/index.json) reflects edits without a manual rebuild step."""
    import http.server
    import functools
    import threading

    build_index()
    stop = threading.Event()

    def watch() -> None:
        last = _mtimes()
        while not stop.is_set():
            time.sleep(1.5)
            current = _mtimes()
            if current != last:
                last = current
                build_index()

    t = threading.Thread(target=watch, daemon=True)
    t.start()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(REPO_ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/journal/calendar.html"
    print(f"Serving {REPO_ROOT} — open {url}")
    print("Editing journal/<date>/tasks.md or notes.md auto-rebuilds the index; the page polls it every few seconds.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to today")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("new", help="scaffold today's (or --date's) journal folder")

    p_task = sub.add_parser("task", help="append a task to a day's tasks.md")
    p_task.add_argument("text")
    p_task.add_argument("--done", action="store_true")

    p_note = sub.add_parser("note", help="append a paragraph to a day's notes.md")
    p_note.add_argument("text")

    sub.add_parser("index", help="rebuild journal/index.json from all day folders")

    p_serve = sub.add_parser("serve", help="serve the calendar locally with a live-updating index")
    p_serve.add_argument("--port", type=int, default=8420)

    args = parser.parse_args()
    d = args.date or today_str()

    if args.command == "new":
        ensure_day(d)
        print(f"journal/{d}/")
    elif args.command == "task":
        add_task(d, args.text, done=args.done)
    elif args.command == "note":
        add_note(d, args.text)
    elif args.command == "index":
        build_index()
        print(f"wrote journal/index.json ({len((JOURNAL_DIR / 'index.json').read_text())} bytes)")
    elif args.command == "serve":
        serve(port=args.port)
    else:
        sys.exit(parser.format_usage())


if __name__ == "__main__":
    main()
