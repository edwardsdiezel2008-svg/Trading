# Daybreak Ledger

A 60-day trading journal dashboard: one glossy box per day, click today's (or any past)
box to write a short thesis on what you did and mark the day positive (green) or
negative (red). Covers 2026-08-19 through 2026-10-17.

**Live, saving version:** https://claude.ai/code/artifact/31999da3-0054-4442-b4a3-e05486b51992
Entries written there persist automatically (it runs on Claude's artifact runtime).

`index.html` in this folder is the same page as a static snapshot — open it locally to
preview the design, but it has no backend, so entries typed here don't save anywhere;
use the live link above for the real thing.

## Nightly reminder

A scheduled routine pings a push notification every night at 9:00 PM (Mountain Time /
Alberta) asking for that day's thesis, linking back to the live dashboard. It starts
the day after this was set up (2026-08-20), not the same day it was created.
