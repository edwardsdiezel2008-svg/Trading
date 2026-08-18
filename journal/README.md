# Daily journal + live calendar planner

One folder per day of work on this project — a running record of tasks and
conversation notes, browsable as a live monthly calendar.

## Layout

```
journal/
  2026-08-18/
    tasks.md    # checklist: - [ ] pending   - [x] done
    notes.md    # free-text notes/summary; first line is the day's title
  index.json    # generated - do not hand-edit, see below
  calendar.html # the live calendar planner UI, reads index.json
```

## Logging a day's work

```bash
python scripts/journal.py new                       # scaffold today's folder
python scripts/journal.py task "wire up the X"       # append a pending task
python scripts/journal.py task "fixed the bug" --done
python scripts/journal.py note "why we did it this way"
python scripts/journal.py --date 2026-08-05 task "backfilled entry"
```

You can also just edit `journal/<date>/tasks.md` and `notes.md` directly -
`task`/`note` are a convenience, not the only way in.

## The live calendar

`journal/calendar.html` is a self-contained static page that renders a
month grid, marks days that have entries, and shows each day's tasks/notes
in a side panel on click. It reads `journal/index.json`, which is built
from every day folder by:

```bash
python scripts/journal.py index
```

To make it actually *live* - i.e. reflect edits without a manual rebuild or
page refresh - run:

```bash
python scripts/journal.py serve
```

This serves the repo locally, rebuilds `journal/index.json` automatically
whenever a `tasks.md`/`notes.md` changes (polled every ~1.5s), and the page
itself polls `index.json` every few seconds - so editing a task file and
watching the calendar update is the normal workflow.

`journal/index.json` is committed as a snapshot so the calendar also works
if you just open `calendar.html` from a server without running `serve`
first (browsers block `fetch()` against `file://`, so a plain double-click
open won't load data - use `serve`, or any static file server, instead).
