# BTC/USDT paper trading

Simulated (no real money) live trading of all 7 strategies against real
BTC/USDT daily bars, updated roughly hourly by a scheduled agent check-in.

## How it actually works

There's no standalone bot process - this environment's scheduled triggers
fire a prompt into the Claude session, which then does the update by hand
each time:

1. Pull the latest daily candle(s) for BTC_USDT via the Crypto.com MCP
   connector (`mcp__Crypto_com__get_candlestick`) - this is the one live
   data path that works from within the session; direct HTTP calls to
   market data APIs are blocked by this environment's network policy.
2. Upsert those candles into `bars.csv` (today's row gets overwritten as it
   updates through the day; a new row is appended when a new day starts).
3. Run `python scripts/paper_trade_update.py`, which re-runs the same
   tested backtest engine (`src/backtest/engine.py`) on the full bar
   history for every strategy and derives each one's current position from
   the last bar of a fresh, complete backtest - no separate incremental
   "live execution" logic that could drift out of sync with what the
   engine actually validated.
4. Commit and push `bars.csv`, `positions.json`, `trade_log.csv`, and
   `summary.md` so state survives container restarts.
5. Only send a chat message if a strategy's position actually changed
   since the last check - silent otherwise.

## Files

- `bars.csv` - growing daily OHLCV history, the only file fed by live data.
- `positions.json` - current position, unrealized equity, and open trade
  (if any) per strategy, plus when it was last updated.
- `trade_log.csv` - every closed trade across all 7 strategies.
- `summary.md` - human-readable snapshot table.

## Caveats

- **Hourly, not real-time.** Scheduled triggers in this environment have a
  one-hour minimum interval. This checks in on a real market roughly once
  an hour; it does not react intraday.
- **"Today" is provisional.** BTC/USDT trades 24/7 and Crypto.com's current-day
  candle updates continuously until the day rolls over. A position derived
  from today's still-forming candle reflects "if today closed here," not a
  finalized signal - by the time it would actually execute (next day's
  open, per this engine's execution model), the number may have moved.
- **No real capital, no real slippage/latency.** This proves whether a
  strategy's logic would have kept working on real, ongoing price action -
  it is not a substitute for actually trading, and nothing here should be
  read as investment advice.
