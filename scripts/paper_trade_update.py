"""Regenerate paper-trading state from the current bar history, for a given
track (timeframe).

Deliberately has no incremental state logic: given a growing, append-only
bars CSV, this just re-runs the same tested backtest engine on the full
history for every strategy and derives "current position" from the last bar
of a fresh, complete backtest. That avoids an entire class of bugs that
live-execution/incremental-update code is prone to (state drift, double-
counting, missed updates) - the tradeoff is O(bars) work each run, trivial
at these data sizes.

This script does NOT fetch data itself - it has no network access here. The
bars file must already be updated with the latest candle(s) before calling
this (see paper_trading/README.md).

Usage:
  python scripts/paper_trade_update.py                                       # daily track (default)
  python scripts/paper_trade_update.py --suffix _15m --freq 15min --tracking-start "2026-08-08 08:45:00"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import pandas as pd

from src.backtest.data_loader import load_bars
from src.backtest.engine import run_backtest
from src.backtest.instruments import get_spec
from src.backtest.metrics import compute_metrics
from src.backtest.strategies import ALL_STRATEGY_CLASSES
from src.backtest.strategies.cost_filter import CostAwareFilter

CAPITAL = 100_000.0
# Real accounts never let equity go arbitrarily negative - a broker/exchange
# liquidates you first. Force-close any open position once it's lost half
# the equity that was allocated to it, applied to every paper-trading track
# (not just the one that happened to hit this) so the whole dashboard
# reflects a bounded, realistic risk floor rather than raw unbounded
# backtest math. See src/backtest/engine.py's max_loss_fraction docstring.
MAX_LOSS_FRACTION = 0.5

# --- Leveraged/perpetual-futures specific helpers (only active when
# --leverage != 1.0) ---

# 0.5% - a reasonable, clearly-approximate stand-in for a real exchange's
# lowest-tier BTC perpetual maintenance margin requirement. Real schedules
# vary by position size/tier; this system doesn't model per-tier margin.
MAINTENANCE_MARGIN_RATIO = 0.005


def perp_max_loss_fraction(leverage: float) -> float:
    """How much of the equity allocated to a leveraged position must be lost
    before it's force-closed - standing in for a real exchange's margin
    call/liquidation. At leverage L, a price move of roughly 1/L against the
    position wipes the margin backing it; real liquidation happens a bit
    before that, once only MAINTENANCE_MARGIN_RATIO worth of margin remains.
    Higher leverage means liquidation is both a smaller *price move* away
    and (correctly) a larger *fraction of allocated margin* lost - a single
    blanket loss-fraction like the 0.5 used for the unleveraged tracks would
    either be economically meaningless at leverage or force-close far too
    early relative to how real margin trading actually works."""
    return max(0.0, 1.0 - leverage * MAINTENANCE_MARGIN_RATIO)


def liquidation_price(entry_price, direction: int, leverage: float, max_loss_fraction: float):
    """Price at which a leveraged position would be force-closed under
    perp_max_loss_fraction, given its entry price and direction. None for a
    flat or unleveraged position, where liquidation isn't a meaningful
    concept."""
    if direction == 0 or leverage <= 1.0 or entry_price is None:
        return None
    adverse_frac = max_loss_fraction / leverage
    if direction > 0:
        return entry_price * (1 - adverse_frac)
    return entry_price * (1 + adverse_frac)


def accrue_funding(prior_accrued_usd, prior_ts, now, direction: int, notional, funding_rate, min_interval_minutes: float = 30.0):
    """Adds this check-in's funding cost/credit to a running total, guarded
    against re-applying within min_interval_minutes (protects against a
    manual re-trigger double-charging funding that a real ~hourly cadence
    wouldn't). Applies the currently-reported live funding rate once per
    check-in that clears the guard, directly - not scaled to a specific
    settlement interval, since this system has no way to verify Crypto.com
    perpetuals' exact funding cadence without live access to their API
    docs. Funding is zero-sum for the position holder: a positive rate is
    paid BY longs TO shorts (and vice versa for a negative rate), so
    direction - not just price - determines the sign.

    Returns (new_accrued_usd, new_timestamp, applied). The very first call
    for a strategy (prior_ts is None) only establishes the baseline
    timestamp and never backdates an accrual - funding tracking starts from
    when this feature launched, not from whenever the position happened to
    have actually opened."""
    prior_accrued_usd = prior_accrued_usd or 0.0
    if prior_ts is None:
        return prior_accrued_usd, now, True
    elapsed_minutes = (now - prior_ts).total_seconds() / 60.0
    if elapsed_minutes < min_interval_minutes:
        return prior_accrued_usd, prior_ts, False
    delta = 0.0
    if direction != 0 and funding_rate is not None and notional:
        delta = -direction * notional * funding_rate
    return prior_accrued_usd + delta, now, True


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suffix", default="", help="File suffix distinguishing this track, e.g. '_15m'. Default '' = the original daily track.")
    p.add_argument("--freq", default="1D", help="Pandas freq string for bar resampling/annualization, e.g. '1D', '15min'.")
    p.add_argument("--tracking-start", default="2026-08-08", help="Timestamp (parseable by pandas) marking where the live track record begins.")
    p.add_argument("--symbol", default="BTC_USDT", help="Instrument symbol for backtest spec lookup and metadata, e.g. 'ETH_USDT', 'SOL_USDT'.")
    p.add_argument("--cost-aware-min-multiple", type=float, default=None,
                    help="If set, wraps every strategy in CostAwareFilter: a position change is only taken when "
                         "the bar's ATR-based expected move is at least this many multiples of the round-trip "
                         "transaction cost. Meant for sub-daily tracks (e.g. 15-minute) where reusing daily-tuned "
                         "strategy periods causes far more trades than the typical bar-to-bar move can pay for. "
                         "Off by default so daily/ETH/SOL tracks are unaffected.")
    p.add_argument("--leverage", type=float, default=1.0,
                    help="Position notional as a multiple of equity (passed through to run_backtest's "
                         "capital_fraction). 1.0 (default) matches every existing spot track exactly. Above 1.0 "
                         "switches this track to perpetual-futures-style leveraged sizing: max_loss_fraction is "
                         "computed from leverage (see perp_max_loss_fraction) instead of the flat 0.5 used "
                         "elsewhere, and a liquidation price + live funding-rate accrual are tracked per strategy.")
    p.add_argument("--bars-file", default=None,
                    help="Explicit bars CSV path, overriding the default paper_trading/bars<suffix>.csv - lets a "
                         "leveraged track reuse an existing spot track's bars (e.g. bars.csv for a BTC perp track) "
                         "without a separate data fetch.")
    return p.parse_args(argv)


def _downsample_equity_curve(index, equity_curve, max_points=250):
    """The full backtest equity curve (one point per bar) is otherwise
    computed and thrown away - downsample it for the dashboard's full-
    history equity chart instead of embedding thousands of points per
    strategy. Always keeps the first and last point."""
    n = len(equity_curve)
    if n <= max_points:
        idxs = range(n)
    else:
        stride = (n - 1) / (max_points - 1)
        idxs = sorted({round(i * stride) for i in range(max_points)})
    return [[str(index[i]), round(float(equity_curve.iloc[i]), 2)] for i in idxs]


def _buy_and_hold_curve(bars, capital):
    """The obvious question the strategy comparison chart couldn't answer on
    its own: would just holding the asset have done better than any of
    this? No costs modeled - a single buy at the first bar and a single
    sell at the last, whose two-trade cost is negligible next to a multi-
    year hold."""
    initial_price = bars["close"].iloc[0]
    if not initial_price:
        return pd.Series(capital, index=bars.index)
    return capital * (bars["close"] / initial_price)


def _update_track_record(bars, strategy_name, result, capital, tracking_start, track_record_path):
    if tracking_start in bars.index:
        start_idx = bars.index.get_loc(tracking_start)
    else:
        # Tracking start predates the bar history we have, or hasn't arrived
        # yet - fall back to the first bar so we don't crash.
        start_idx = 0

    eq = result.equity_curve
    equity_at_start = eq.iloc[start_idx - 1] if start_idx > 0 else capital
    current_equity = eq.iloc[-1]
    return_since_start = current_equity / equity_at_start - 1 if equity_at_start else 0.0

    latest_bar_key = str(bars.index[-1])
    row = {
        "date": latest_bar_key,
        "strategy": strategy_name,
        "equity": round(current_equity, 2),
        "return_since_tracking_start_pct": round(return_since_start * 100, 3),
        "position": result.positions.iloc[-1],
    }

    if os.path.exists(track_record_path):
        existing = pd.read_csv(track_record_path)
        existing = existing[~((existing["date"] == latest_bar_key) & (existing["strategy"] == strategy_name))]
        updated = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        updated = pd.DataFrame([row])
    updated = updated.sort_values(["date", "strategy"])
    updated.to_csv(track_record_path, index=False)


def _load_btc_funding_rate(path="paper_trading/btc_market_snapshot.json"):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            snap = json.load(f)
        rate = (snap.get("funding_rate") or {}).get("rate")
        return float(rate) if rate is not None else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def main(argv=None):
    args = parse_args(argv)
    bars_path = args.bars_file or f"paper_trading/bars{args.suffix}.csv"
    positions_path = f"paper_trading/positions{args.suffix}.json"
    trade_log_path = f"paper_trading/trade_log{args.suffix}.csv"
    track_record_path = f"paper_trading/track_record{args.suffix}.csv"
    summary_path = f"paper_trading/summary{args.suffix}.md"
    tracking_start = pd.Timestamp(args.tracking_start)

    bars = load_bars(bars_path, freq=args.freq)
    spec = get_spec(args.symbol)

    is_leveraged = args.leverage != 1.0
    max_loss_fraction = perp_max_loss_fraction(args.leverage) if is_leveraged else MAX_LOSS_FRACTION

    prior_positions = {}
    funding_rate = None
    now = datetime.now(timezone.utc)
    if is_leveraged:
        funding_rate = _load_btc_funding_rate()
        if os.path.exists(positions_path):
            with open(positions_path) as f:
                prior_positions = (json.load(f).get("strategies")) or {}

    positions = {}
    all_trades = []
    summary_rows = []

    for cls in ALL_STRATEGY_CLASSES:
        strat = cls()
        if args.cost_aware_min_multiple is not None:
            strat = CostAwareFilter(strat, spec, min_cost_multiple=args.cost_aware_min_multiple)
        result = run_backtest(bars, strat, spec, initial_capital=CAPITAL, max_loss_fraction=max_loss_fraction, capital_fraction=args.leverage)
        metrics = compute_metrics(result, CAPITAL, freq_hint=args.freq)
        _update_track_record(bars, strat.name, result, CAPITAL, tracking_start, track_record_path)

        last_pos = int(result.positions.iloc[-1])
        last_equity = float(result.equity_curve.iloc[-1])
        open_trade = None
        if result.trades and result.trades[-1].exit_time == bars.index[-1] and last_pos != 0:
            # engine force-closes any still-open position at the final bar for
            # reporting purposes; if we're still holding as of the latest bar,
            # treat that synthetic close as "still open" for paper-trading state.
            t = result.trades[-1]
            open_trade = {"direction": t.direction, "entry_price": t.entry_price, "entry_time": str(t.entry_time), "units": t.units}
            closed_trades = result.trades[:-1]
        else:
            closed_trades = result.trades

        pos_entry = {
            "position": last_pos,
            "position_label": "LONG" if last_pos > 0 else "SHORT" if last_pos < 0 else "FLAT",
            "equity": round(last_equity, 2),
            "open_trade": open_trade,
            "as_of": str(bars.index[-1]),
            "equity_curve": _downsample_equity_curve(bars.index, result.equity_curve),
        }

        if is_leveraged:
            liq_price = liquidation_price(open_trade["entry_price"], last_pos, args.leverage, max_loss_fraction) if open_trade else None
            notional = (open_trade["units"] * float(bars["close"].iloc[-1])) if open_trade else 0.0
            prior_strat = prior_positions.get(strat.name) or {}
            prior_accrued = prior_strat.get("funding_accrued_usd")
            prior_ts_str = prior_strat.get("funding_last_accrued_utc")
            prior_ts = pd.Timestamp(prior_ts_str).to_pydatetime() if prior_ts_str else None
            accrued, ts, _applied = accrue_funding(prior_accrued, prior_ts, now, last_pos, notional, funding_rate)
            pos_entry["liquidation_price"] = liq_price
            pos_entry["funding_accrued_usd"] = round(accrued, 4)
            pos_entry["funding_last_accrued_utc"] = ts.isoformat()

        positions[strat.name] = pos_entry

        for t in closed_trades:
            all_trades.append({
                "strategy": strat.name,
                "direction": "LONG" if t.direction > 0 else "SHORT",
                "entry_time": str(t.entry_time),
                "exit_time": str(t.exit_time),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "net_pnl": round(t.net_pnl, 2),
            })

        summary_rows.append((strat.name, last_pos, last_equity, metrics["total_return"], metrics["sharpe"], metrics["num_trades"]))

    with open(positions_path, "w") as f:
        json.dump({
            "symbol": args.symbol,
            "freq": args.freq,
            "leverage": args.leverage,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "latest_bar": str(bars.index[-1]),
            "bar_count": len(bars),
            "buy_and_hold_equity_curve": _downsample_equity_curve(bars.index, _buy_and_hold_curve(bars, CAPITAL)),
            "strategies": positions,
        }, f, indent=2)

    pd.DataFrame(all_trades).to_csv(trade_log_path, index=False)

    lines = [
        f"# {args.symbol.replace('_', '/')} Paper Trading ({args.freq}) — updated {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Latest bar: {bars.index[-1]} · {len(bars):,} bars of history · ${CAPITAL:,.0f} starting capital per strategy",
        "",
        "| Strategy | Position | Equity | Total Return | Sharpe | Trades |",
        "|---|---|---|---|---|---|",
    ]
    bh_final = float(_buy_and_hold_curve(bars, CAPITAL).iloc[-1])
    bh_return = bh_final / CAPITAL - 1
    lines.append(f"| *Buy & Hold (benchmark)* | — | ${bh_final:,.0f} | {bh_return*100:+.1f}% | — | 1 |")
    for name, pos, equity, total_ret, sharpe, n_trades in sorted(summary_rows, key=lambda r: -r[3]):
        label = "LONG" if pos > 0 else "SHORT" if pos < 0 else "FLAT"
        sharpe_str = f"{sharpe:.2f}" if sharpe == sharpe else "—"  # NaN check
        lines.append(f"| {name} | {label} | ${equity:,.0f} | {total_ret*100:+.1f}% | {sharpe_str} | {n_trades} |")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Updated {positions_path}, {trade_log_path}, {summary_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
