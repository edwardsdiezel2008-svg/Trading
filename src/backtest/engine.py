"""Backtest engine: turns a strategy's target-position signal into simulated
fills, an equity curve, and a trade log.

Execution model (kept deliberately simple and explicit, to avoid the two
classic backtesting sins - lookahead bias and silently-wrong P&L):

  * A signal computed using bars up to and including bar t is only ever
    acted on starting at the OPEN of bar t+1 - you can't trade on
    information you don't have yet.
  * While a position is held unchanged, P&L is marked to market every bar
    using open/close, so the equity curve (and therefore drawdown) reflects
    intrabar-to-intrabar reality, not just realized trade P&L.
  * Position size is recomputed only when a new leg opens (not intrabar),
    either as a fixed number of units or as a fraction of current equity
    (see `_position_size`). Futures margin is NOT modeled - percent_equity
    sizing uses notional value, which is a simplification; for futures the
    safer default is fixed_units.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .instruments import InstrumentSpec


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int  # 1 = long, -1 = short
    entry_price: float
    exit_price: float
    units: float
    gross_pnl: float
    costs: float
    net_pnl: float
    entry_equity: float

    @property
    def return_pct(self) -> float:
        return self.net_pnl / self.entry_equity if self.entry_equity else 0.0

    @property
    def bars_held(self) -> int:
        return getattr(self, "_bars_held", 0)


@dataclass
class BacktestResult:
    strategy_name: str
    instrument: str
    bars: pd.DataFrame
    signals: pd.Series
    positions: pd.Series
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)


def _trade_cost(units: float, price: float, spec: InstrumentSpec, slippage_ticks: float) -> float:
    """Fixed per-unit costs (equities/futures: commission_per_unit + tick-based
    slippage) plus percentage-of-notional costs (crypto: commission_pct +
    slippage_pct) - additive so existing fixed-cost specs are unaffected by
    the percentage fields defaulting to 0.0."""
    fixed = units * (spec.commission_per_unit + slippage_ticks * spec.tick_size)
    notional = units * price * spec.multiplier
    pct = notional * (spec.commission_pct + spec.slippage_pct)
    return fixed + pct


def _position_size(
    equity: float,
    price: float,
    spec: InstrumentSpec,
    capital_fraction: float,
    sizing: str,
    fixed_units: float,
) -> float:
    # Checked before the sizing branch, not just inside percent_equity's: a
    # blown account (equity <= 0) must never re-enter, in fixed_units mode
    # too - fixed_units sizing doesn't derive size from equity, so without
    # this it would keep opening fixed-size trades forever after max_loss_
    # fraction's force-close, contradicting this module's own stated intent
    # that a real account gets liquidated, not left to keep trading a wiped
    # margin. Futures tracks (this system's only fixed_units users) default
    # to fixed_units, so this guard is what actually makes max_loss_fraction
    # a real floor for them rather than just a delay before ruin.
    if equity <= 0:
        return 0.0
    if sizing == "fixed_units":
        return float(fixed_units)
    notional_per_unit = price * spec.multiplier
    if notional_per_unit <= 0:
        return 0.0
    raw_units = (equity * capital_fraction) / notional_per_unit
    if spec.fractional_units:
        return max(raw_units, 0.0)
    # Stocks/futures trade in whole shares/contracts - flooring is correct there,
    # but would silently zero out any position sizing for a fractional asset
    # (e.g. $100 of equity can't buy a whole "1 unit" of $65k BTC).
    return max(np.floor(raw_units), 0.0)


def run_backtest(
    bars: pd.DataFrame,
    strategy,
    spec: InstrumentSpec,
    initial_capital: float = 100_000.0,
    capital_fraction: float = 1.0,
    sizing: str | None = None,
    fixed_units: float = 1.0,
    slippage_ticks: float = 1.0,
    max_loss_fraction: float | None = None,
    max_drawdown_fraction: float | None = 0.05,
) -> BacktestResult:
    """Run one strategy over one instrument's bars.

    sizing: 'percent_equity' or 'fixed_units'. Defaults to 'fixed_units' for
    futures (margin isn't modeled, so notional sizing is unreliable there)
    and 'percent_equity' for equities.

    max_loss_fraction: if set, force-closes an open position the moment its
    mark-to-market loss reaches this fraction of the equity that was
    allocated to it at entry - simulating a stop-loss/margin-call floor a
    real account would hit. Off by default (None), which is the original,
    unbounded behavior: without it, a short position sized at 100% of
    equity has no ceiling on how far the market can move against it before
    the position is closed, so equity can go arbitrarily negative (e.g. a
    short held through a 3x rally). Real accounts never let that happen -
    they liquidate you first.

    max_drawdown_fraction: a portfolio-wide circuit breaker, distinct from
    max_loss_fraction's per-trade stop. Tracks equity's running peak; the
    moment current equity falls this fraction below that peak, any open
    position is force-closed and the strategy is halted flat for the
    *remainder of the backtest* - no re-entry even if the signal later
    wants one. Defaults to 0.05 (5%) so every caller gets this floor unless
    it explicitly opts out with max_drawdown_fraction=None. A test that
    means to exercise unbounded/extreme-drawdown behavior on purpose (e.g.
    to isolate max_loss_fraction's own force-close, or NaN propagation)
    needs to pass None explicitly - otherwise this breaker fires first.
    """
    if sizing is None:
        sizing = "fixed_units" if spec.asset_class == "future" else "percent_equity"

    signals = strategy.generate_signals(bars).reindex(bars.index).fillna(0)
    target_positions = signals.shift(1).fillna(0)  # decided at close(t-1), executed at open(t)

    open_ = bars["open"].to_numpy()
    close = bars["close"].to_numpy()
    n = len(bars)

    equity = initial_capital
    equity_curve = np.empty(n)
    positions_held = np.empty(n)

    current_direction = 0
    current_units = 0.0
    current_entry_cost = 0.0
    entry_price = None
    entry_time = None
    entry_equity = None
    entry_bar_idx = None
    trades: list[Trade] = []
    peak_equity = initial_capital
    halted = False

    target = target_positions.to_numpy()

    for i in range(n):
        # Once max_drawdown_fraction has halted the strategy, no new entry is
        # ever taken again - override whatever the signal wants with flat.
        p = 0 if halted else int(target[i])
        o = open_[i]
        c = close[i]

        # 1. Mark-to-market the gap from the previous close to this bar's open,
        #    using the position (and size) that was in force before any trade this bar.
        if i > 0 and current_direction != 0:
            equity += current_units * current_direction * (o - close[i - 1]) * spec.multiplier

        # 2. If the target position differs from what we're holding, execute at this open.
        if p != current_direction:
            if current_direction != 0:
                # Close the existing leg.
                exit_cost = _trade_cost(current_units, o, spec, slippage_ticks)
                equity -= exit_cost
                gross_pnl = current_units * current_direction * (o - entry_price) * spec.multiplier
                trade = Trade(
                    entry_time=entry_time,
                    exit_time=bars.index[i],
                    direction=current_direction,
                    entry_price=entry_price,
                    exit_price=o,
                    units=current_units,
                    gross_pnl=gross_pnl,
                    costs=current_entry_cost + exit_cost,
                    net_pnl=gross_pnl - current_entry_cost - exit_cost,
                    entry_equity=entry_equity,
                )
                trade._bars_held = i - entry_bar_idx
                trades.append(trade)
                current_direction = 0
                current_units = 0.0
                current_entry_cost = 0.0

            if p != 0:
                new_units = _position_size(equity, o, spec, capital_fraction, sizing, fixed_units)
                entry_cost = _trade_cost(new_units, o, spec, slippage_ticks)
                if new_units > 0:
                    equity -= entry_cost
                    current_direction = p
                    current_units = new_units
                    current_entry_cost = entry_cost
                    entry_price = o
                    entry_time = bars.index[i]
                    entry_equity = equity
                    entry_bar_idx = i
                else:
                    current_direction = 0

        # 3. Mark-to-market this bar's open-to-close move for whatever we're now holding.
        if current_direction != 0:
            equity += current_units * current_direction * (c - o) * spec.multiplier

        # 4. Portfolio-wide drawdown breaker: force-close (if a position is open)
        #    and halt ALL future trading the moment equity falls max_drawdown_
        #    fraction below its running peak. Unlike max_loss_fraction below,
        #    there is no fresh entry afterward - this bar's `halted = True`
        #    makes every subsequent bar's target position 0 (see top of loop).
        if not halted and max_drawdown_fraction is not None:
            peak_equity = max(peak_equity, equity)
            if peak_equity > 0 and (peak_equity - equity) / peak_equity >= max_drawdown_fraction:
                if current_direction != 0:
                    exit_cost = _trade_cost(current_units, c, spec, slippage_ticks)
                    equity -= exit_cost
                    gross_pnl = current_units * current_direction * (c - entry_price) * spec.multiplier
                    trade = Trade(
                        entry_time=entry_time,
                        exit_time=bars.index[i],
                        direction=current_direction,
                        entry_price=entry_price,
                        exit_price=c,
                        units=current_units,
                        gross_pnl=gross_pnl,
                        costs=current_entry_cost + exit_cost,
                        net_pnl=gross_pnl - current_entry_cost - exit_cost,
                        entry_equity=entry_equity,
                    )
                    trade._bars_held = i - entry_bar_idx
                    trades.append(trade)
                    current_direction = 0
                    current_units = 0.0
                    current_entry_cost = 0.0
                halted = True

        # 5. Stop-loss/liquidation floor: force-close if this leg's mark-to-market
        #    loss has reached max_loss_fraction of the equity it was opened with.
        #    A fresh entry next bar is still possible if the signal still wants one.
        if current_direction != 0 and max_loss_fraction is not None and entry_equity:
            loss_frac = 1.0 - equity / entry_equity
            if loss_frac >= max_loss_fraction:
                exit_cost = _trade_cost(current_units, c, spec, slippage_ticks)
                equity -= exit_cost
                gross_pnl = current_units * current_direction * (c - entry_price) * spec.multiplier
                trade = Trade(
                    entry_time=entry_time,
                    exit_time=bars.index[i],
                    direction=current_direction,
                    entry_price=entry_price,
                    exit_price=c,
                    units=current_units,
                    gross_pnl=gross_pnl,
                    costs=current_entry_cost + exit_cost,
                    net_pnl=gross_pnl - current_entry_cost - exit_cost,
                    entry_equity=entry_equity,
                )
                trade._bars_held = i - entry_bar_idx
                trades.append(trade)
                current_direction = 0
                current_units = 0.0
                current_entry_cost = 0.0

        equity_curve[i] = equity
        positions_held[i] = current_direction

    # Close any position still open at the end of the data, at the last close.
    if current_direction != 0:
        last_price = close[-1]
        exit_cost = _trade_cost(current_units, last_price, spec, slippage_ticks)
        gross_pnl = current_units * current_direction * (last_price - entry_price) * spec.multiplier
        trade = Trade(
            entry_time=entry_time,
            exit_time=bars.index[-1],
            direction=current_direction,
            entry_price=entry_price,
            exit_price=last_price,
            units=current_units,
            gross_pnl=gross_pnl,
            costs=current_entry_cost + exit_cost,
            net_pnl=gross_pnl - current_entry_cost - exit_cost,
            entry_equity=entry_equity,
        )
        trade._bars_held = (n - 1) - entry_bar_idx
        trades.append(trade)
        equity_curve[-1] -= exit_cost

    return BacktestResult(
        strategy_name=strategy.name,
        instrument=spec.symbol,
        bars=bars,
        signals=signals,
        positions=pd.Series(positions_held, index=bars.index),
        equity_curve=pd.Series(equity_curve, index=bars.index),
        trades=trades,
    )
