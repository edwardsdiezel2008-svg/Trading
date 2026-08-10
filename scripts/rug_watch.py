"""Shared "Rug Pull Watch" severity logic - a single source of truth for the
thresholds used by both memecoin_wide_scan.py (which logs flagged-coin
history each hourly run) and build_paper_trading_dashboard.py (which
summarizes that history for the landing page). The full flagged-coin table
on dashboard.html re-implements the same thresholds in JS, since that page
has no build step to share Python code with - keep the three in sync
manually if these ever change.

Severity is a price-crash proxy from CEX ticker data (24h change and
drawdown from the 24h high), not on-chain rug-pull detection - see the
panel copy in dashboard_template.html for the full caveat.
"""
from __future__ import annotations

SEVERE = {"change": -30, "from_high": -40}
ELEVATED = {"change": -15, "from_high": -25}

HISTORY_PATH = "paper_trading/rug_watch_history.json"
HISTORY_MAX_ENTRIES = 168  # ~7 days at hourly cadence


def severity_for(coin: dict) -> str | None:
    change = coin.get("change_24h_pct", 0)
    from_high = coin.get("pct_from_24h_high", 0)
    if change <= SEVERE["change"] or from_high <= SEVERE["from_high"]:
        return "severe"
    if change <= ELEVATED["change"] or from_high <= ELEVATED["from_high"]:
        return "elevated"
    return None


def severity_for_multiday_drawdown(pct_from_window_high: float) -> str | None:
    """Same drawdown thresholds as severity_for(), applied to a longer-
    window high (e.g. the ~12-day precise-scan history in
    memecoin_scan_update.py) instead of the 24h ticker snapshot - catches a
    coin that peaked a few days ago and has been grinding down since,
    which a single day's change could easily miss."""
    if pct_from_window_high <= SEVERE["from_high"]:
        return "severe"
    if pct_from_window_high <= ELEVATED["from_high"]:
        return "elevated"
    return None
