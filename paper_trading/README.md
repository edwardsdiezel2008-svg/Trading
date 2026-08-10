# Crypto + index futures paper trading cockpit

Simulated (no real money) live trading of 12 backtested strategies across 16
tracks - BTC (daily, 15-minute, 3x leveraged perpetual daily, 3x leveraged
perpetual 15-minute), ETH (daily, 3x leveraged perpetual), SOL (daily, 3x
leveraged perpetual), and real CME futures across four markets - Nasdaq-100
(NQ=F/MNQ), S&P 500 (ES=F/MES), Dow (YM=F/MYM), and Gold (GC=F/MGC), each
daily and 5-minute - against real Crypto.com Exchange and Yahoo Finance
data, plus a wide memecoin momentum/breakout scanner, updated hourly.

**Live site:** the root of this repo's GitHub Pages deployment is the
minimal landing page; `/dashboard.html` is the full detail page with every
track, chart, and table; `/learn.html` is a static methodology/glossary
page - what each strategy trades, how results get validated (walk-forward,
param stability, cross-asset robustness), and what every metric on the
dashboard means.

## How it actually works

There is no standalone bot process and no dependency on a Claude chat
session or MCP connector being open. `.github/workflows/hourly-market-data.yml`
runs on GitHub's own infrastructure every hour (`cron: "10 * * * *"`, plus
manual `workflow_dispatch`):

1. `scripts/fetch_market_data.py` - plain HTTP against Crypto.com Exchange's
   public REST API (no auth needed) for BTC/ETH/SOL candles, the wide
   memecoin ticker universe, BTC order book + perpetual funding rate;
   `scripts/fetch_index_futures.py` pulls real NQ=F, ES=F, YM=F, and GC=F
   (CME Nasdaq-100, S&P 500, and Dow E-mini futures, plus COMEX Gold)
   daily and 5-minute bars from Yahoo Finance's free, keyless chart
   endpoint (see "Index Futures" below); and `scripts/fetch_news.py` pulls
   crypto headlines from public RSS feeds (CoinDesk, CoinTelegraph,
   Bitcoin.com).
2. `scripts/paper_trade_update.py` (once per track: BTC daily, BTC
   15-min, BTC Perpetual daily, BTC Perpetual 15-min, ETH, SOL, ETH
   Perpetual, SOL Perpetual, Nasdaq Futures daily, Nasdaq Futures 5-min,
   S&P 500 Futures daily, S&P 500 Futures 5-min, Dow Futures daily, Dow
   Futures 5-min, Gold Futures daily, Gold Futures 5-min)
   re-runs the same tested backtest engine (`src/backtest/engine.py`) on
   the full bar history for every strategy
   and derives each one's current position from the last bar of a fresh,
   complete backtest - no separate incremental "live execution" logic that
   could drift out of sync with what the engine actually validated. Both
   15-minute crypto tracks and each 5-minute futures track also pass
   `--cost-aware-min-multiple 1.0`, wrapping
   every strategy in `CostAwareFilter` (`src/backtest/strategies/cost_filter.py`)
   so it only trades when the recent ATR-based expected move can plausibly
   clear the round-trip transaction cost - reusing daily-tuned strategy
   periods unfiltered on faster bars caused far more whipsaw trades than
   the typical bar-to-bar move could pay for. Each perpetual track passes
   `--leverage 3.0 --bars-file <its spot track's bars file>`, reusing that
   spot track's own bars instead of a separate fetch - see "Perpetual
   futures" below.
3. `scripts/memecoin_scan_update.py` / `scripts/memecoin_wide_scan.py`
   refresh the memecoin breakout scanner and momentum heatmap.
4. `scripts/build_paper_trading_dashboard.py` rebuilds both HTML pages from
   the current state.
5. Commits and pushes everything under `paper_trading/` if anything
   changed, then stages `index.html` + `dashboard.html` + `learn.html` and
   deploys them to GitHub Pages via `actions/deploy-pages@v4`. `learn.html`
   is static (no data placeholders) and isn't touched by the build script -
   it's hand-edited directly and just gets copied through unchanged.

## Risk floor (applies to every live track)

Every `paper_trade_update.py` run applies `max_loss_fraction=0.5` to
`run_backtest()`: an open position is force-closed the moment it's lost
half the equity that was allocated to it, simulating the stop-out a real
account would hit long before equity could go arbitrarily negative. This
is off by default in the engine itself (`max_loss_fraction=None`) and only
enabled for the live paper-trading tracks - walk-forward and sensitivity
snapshots run without it, since those are deliberately testing a
strategy's raw signal edge.

## Perpetual futures (leverage, liquidation, funding)

Four tracks (`_perp` BTC daily, `_perp_15m` BTC 15-minute, `_eth_perp` ETH
daily, `_sol_perp` SOL daily) run the same strategy library against the same
price history as their spot equivalent, but sized at 3x notional exposure
per dollar of equity (`run_backtest(..., capital_fraction=leverage)` - the
engine's existing sizing knob, not new engine code) - same price moves,
amplified gains and losses. 3x sits inside the 1x-5x range widely
recommended for beginners on leveraged crypto futures (multiple trading
guides converge on this range; see Learn page for a link). Two mechanics
this introduces that the spot tracks don't have:

- **Liquidation.** The spot tracks' `max_loss_fraction=0.5` "risk floor"
  would be economically meaningless at leverage (either too early or too
  late depending on leverage), so the perp tracks compute their own
  loss-fraction from a maintenance-margin approximation instead:
  `1 - leverage * 0.005` (`perp_max_loss_fraction()` in
  `scripts/paper_trade_update.py`). 0.5% matches Bybit's published
  lowest-tier maintenance margin rate for BTC/ETH/SOL USDT perpetuals
  (positions up to $2M notional); Binance's base tier is close, ~0.4%. A
  per-position liquidation price is derived from that and shown on each
  perp tab. Known simplification: the engine only checks for a
  liquidation-triggering loss at each bar's *close*, not continuously, so
  a single large candle can jump straight past the threshold instead of
  stopping cleanly at the liquidation price - a leveraged strategy's
  equity can occasionally read as more deeply negative than the
  liquidation math alone implies. This is visibly worse on the more
  volatile ETH/SOL perp tracks than on BTC's.
- **Funding.** Real perpetuals periodically exchange payments between longs
  and shorts to stay anchored to spot price. Crypto.com's public API only
  exposes the *current* funding rate per asset, not a historical series,
  so it's honestly impossible to backtest funding cost over the full
  multi-year history the way price/cost/slippage are. Instead,
  `accrue_funding()` tracks it as a separate, real running total going
  forward: each hourly check-in applies that check-in's live funding rate
  once (direction-signed - longs pay a positive rate, shorts receive it),
  guarded against double-applying on a manual re-trigger within 30
  minutes. Crypto.com Exchange recalculates each asset's funding rate
  every 4 hours but settles it hourly against open positions
  (help.crypto.com/en/articles/4894449-funding-and-session-settlement) -
  applying the live rate once per hourly check-in matches that real
  cadence, not just a rough stand-in for it. `fetch_market_data.py` fetches
  BTC/ETH/SOL perpetual funding rates independently each hour (each
  asset's rate reflects that asset's own long/short positioning, so BTC's
  can't be reused as a proxy for ETH/SOL). This total is shown alongside
  the position but deliberately kept separate from the Total Return/Equity
  figures (which are the historical-backtest numbers, funding-free) rather
  than silently blended into them.

Genuinely useful finding from running all four alongside their spot
equivalents: leverage doesn't just scale returns by a fixed multiple. The
ETH and SOL perpetual tracks have consistently shown far fewer profitable
strategies than their unleveraged spot equivalents (see the live dashboard
for current counts, now across 12 strategies rather than the original 9) -
the same drawdowns that a spot position recovers from can instead trigger a
permanent liquidation at leverage, which compounds very differently over
dozens of trades. That's a real result of the simulation, not a bug in it.

## Index Futures

Eight tracks (`_nq`/`_nq5m`, `_es`/`_es5m`, `_ym`/`_ym5m`, `_gc`/`_gc5m`,
each daily/5-min) run all 12 strategies against **real futures prices** -
CME's Nasdaq-100 E-mini (NQ=F), S&P 500 E-mini (ES=F), and Dow E-mini
(YM=F), plus COMEX Gold (GC=F), all continuous front contracts, fetched
from Yahoo Finance's public `v8/finance/chart` endpoint via the `yfinance`
library (`scripts/fetch_index_futures.py`, generalized from a
Nasdaq-only script once the approach proved out live - see git history).
Each real futures price is paired with its Micro contract's economics in
`src/backtest/instruments.py`: **MNQ** ($2/index-point multiplier,
$0.75/side commission, 0.25-point tick), **MES** ($5/index-point
multiplier, $0.75/side commission, 0.25-point tick), **MYM** ($0.50/point
multiplier, $0.75/side commission, 1-point tick), and **MGC** ($10/oz
multiplier, $0.75/side commission, 0.10-point tick). The Micro contracts
track the identical price level as their full-size counterparts, just at a
fraction of the contract size (1/10th for MNQ/MES/MYM, 1/10th for MGC vs
GC), so this is genuine futures point-value P&L math, not an ETF-proxy
approximation. (An earlier version of the Nasdaq track traded QQQ as a
proxy because Stooq's QQQ endpoint looked usable locally; a live run
showed Stooq actually 404s on that symbol in production, which is what
prompted switching to Yahoo's real futures feed instead of patching the
broken proxy.)

Two honest caveats, both surfaced directly on the dashboard tab:

- **Why unleveraged.** Real overnight margin differs by contract, and
  that's reported as-is rather than flattened to one number: MNQ currently
  requires roughly $1,700-1,900 in CME initial margin against tens of
  thousands of dollars notional (~25-30x implied leverage); MES requires
  roughly $2,400-2,500 in maintenance margin against a similar notional
  range, implying meaningfully lower leverage (~10-15x) - the S&P 500 is
  the less volatile index, and CME's margin-setting reflects that; MYM
  requires roughly $1,400-1,600 in maintenance margin at typical notional
  (~15-20x); MGC requires roughly $1,700 in maintenance margin at typical
  notional (~15-20x) - gold's own volatility profile sits between the
  equity indices. All eight tracks deliberately don't attempt to simulate
  any of these figures: the backtest engine only checks for a
  liquidation-triggering loss at each bar's *close* (same limitation noted
  above for the perpetual tracks), and modeling 15-30x real margin risk
  against bar-close-only checks - even on 5-minute bars - would produce
  either constant false liquidations or a threshold so loose it stops
  meaning anything. All eight tracks run unleveraged instead (position
  size is simply however many whole micro contracts $100,000 of paper
  capital covers), so the margin/leverage figures above are sourced
  context, not something simulated.
- **5-minute data retention.** Yahoo's intraday endpoint only serves the
  trailing ~60 days per request - a Yahoo policy, not a choice made here.
  `fetch_index_futures.py` merges freshly-fetched bars into each 5-minute
  track's CSV every hourly run, the same accumulate-forward pattern already
  used for every other track, so each 5-minute track's own history keeps
  growing past that 60-day window over time.

**Data-quality due diligence.** Before trusting a continuous futures
series enough to build validation on top of it, NQ=F's daily history was
checked for rollover artifacts (a common failure mode: splicing quarterly
contracts can leave fake gaps at expiration boundaries) - zero OHLC
internal-consistency violations across 2,514 daily bars, no non-positive
prices, and ~251 trading days/year (matching the real CME calendar). Every
single-day move over 5% lines up with a real, independently verifiable
historical volatility event (Dec 2018, the Feb-Apr 2020 COVID crash, the
2022 rate-hike selloff), not an artifact. ES=F, YM=F, and GC=F are fetched
via the exact same code path, so the same result is expected but hasn't
been separately re-verified yet for each one.

The Nasdaq Futures tracks have real walk-forward, sensitivity, and
meta-strategy snapshots on file (`walkforward_nq*.json`,
`sensitivity_nq*.json`, `meta_strategy_nq*.json`) - the "🔒 Locked-in
strategy" and "🧠 Meta-strategy selector" panels are live there, not just
placeholder text. As of this writing: the daily track's locked-in pick is
`RSI_Reversion(14,30/70)` (+17.1% out-of-sample, Sharpe 0.77); the 5-minute
track's is `Inside_Bar_Breakout(0.6)` (+6.1% OOS, Sharpe 1.44) - one of the
new pattern-recognition strategies added specifically for intraday
timeframes, and the only strategy that held up walk-forward-robust on the
5-minute track once ORB's session-boundary bug (below) was fixed. The S&P
500 Futures tracks seeded with real data immediately on their first
live run (Yahoo returns full history in one request) and now have their
own real snapshots too (`walkforward_es*.json`, `sensitivity_es*.json`,
`meta_strategy_es*.json`). As of this writing: the daily track's locked-in
pick is `RSI_Reversion(14,30/70)` (+6.6% out-of-sample, Sharpe 0.71, 90%
parameter-stable); the 5-minute track's is `ZScore_Reversion(20,z=2.0)`
(+0.9% OOS, Sharpe 1.64, 86% parameter-stable) - a different winner than
Nasdaq's 5-minute track (`Inside_Bar_Breakout`), a useful cross-check that
these aren't just picking the same strategy everywhere regardless of the
underlying instrument. Dow and Gold Futures were added most recently using
the same proven pipeline; their walk-forward/sensitivity/meta-strategy
snapshots get run once real accumulated bar history exists for them (see
git history / commit log for when that happened).

## Pattern-recognition strategies

Three of the 12 strategies read the raw shape of the candles rather than an
indicator series - added specifically because intraday timeframes (the
5-minute Nasdaq Futures track most of all) show far more of these setups
per session than a daily chart does. All three live in
`src/backtest/strategies/patterns.py` and are standard, publicly documented
setups, not something invented for this project:

- **Engulfing Reversal** - a two-candle reversal: a bullish engulfing
  candle (a green candle whose body fully engulfs the prior red candle's
  body) after a down move signals long; a bearish engulfing candle signals
  short.
- **Inside Bar Breakout** - a consolidation-then-breakout setup: an "inside
  bar" (a bar whose entire range sits inside the prior "mother" bar's
  range) followed by a close beyond the mother bar's high or low.
- **Opening Range Breakout** - the standard 5-minute ORB day-trading setup:
  the high/low of the first few bars of each session becomes the "opening
  range"; a breakout of that range, confirmed by sitting on the same side
  of the session's cumulative VWAP, triggers an entry held until the
  opposite breakout or session end. On daily bars (one bar = one session)
  this correctly never fires - ORB is an inherently intraday concept.

**Bug found and fixed while focusing on the Nasdaq Futures tracks
specifically:** Opening Range Breakout's session boundary was originally a
raw UTC calendar-day split (`bars.index.normalize()`). That's silently
wrong for near-24-hour-traded futures like NQ=F, whose 5-minute bars are
stored as naive UTC timestamps - a midnight-UTC boundary lands around
7-8 PM US/Eastern, in the middle of the overnight Globex session, not the
market open ORB is actually built around (the standard reference is the
NYSE/Nasdaq cash-equity open, 9:30 AM ET). The old boundary could split one
continuous overnight session into two arbitrary pieces, or worse, treat a
genuine breakout as the start of a brand-new "session" with its own
opening range consisting only of itself - permanently unable to break out.
Fixed by anchoring the session boundary to 9:30 AM US/Eastern instead
(`src/backtest/strategies/patterns.py`); a regression test
(`test_opening_range_breakout_session_spans_utc_midnight_correctly`)
locks in the corrected behavior across a UTC-midnight crossing. This
changed ORB's real out-of-sample numbers on the 5-minute Nasdaq Futures
track (from +2.9% to -1.0% walk-forward OOS return) - a bug fix isn't
guaranteed to make a strategy look better, only correct, and that's
reported here rather than quietly re-running until the number looked good.

## Locked-in strategy

Every track's dashboard tab now surfaces a single "🔒 Locked-in strategy"
call-out above the full per-strategy comparison table, computed live in the
browser from that track's walk-forward + sensitivity results (see
"Robustness checks" below): the one strategy, if any, that's simultaneously
profitable on the full backtest, walk-forward-robust on out-of-sample data
(positive out-of-sample return *and* Sharpe), and parameter-stable (at
least half of nearby parameter values were also profitable). If more than
one strategy clears all three bars, the one with the highest out-of-sample
Sharpe wins. If none do, the panel says so explicitly rather than picking
one anyway. This only has something to show once a track has an actual
walk-forward + sensitivity snapshot on file - brand new tracks like Nasdaq
Futures (5-min) will read "not enough history yet" until one is run against
real accumulated data.

## Meta-strategy selector

`scripts/meta_strategy_snapshot.py` (methodology in
`src/backtest/meta_strategy.py`) answers a different question than the
locked-in strategy above: not "which single strategy has the best overall
track record," but "which strategy should be trusted *given the current
market regime*." Built directly on `src/backtest/regime.py`'s existing
ADX-based trend/volatility classification and per-regime P&L attribution -
no new regime detection, just a decision layer on top of it:

1. Split the bar history into the same chronological, expanding-window
   folds `walkforward.py` uses.
2. On each fold's TRAIN window only: run every strategy's full backtest at
   its default parameters, bucket each one's P&L by regime
   (`attribute_performance()`), and for each regime pick whichever strategy
   had the best mean P&L per bar *while that regime was in effect* - but
   only if that regime saw at least `--min-regime-bars` (default 20) bars
   of history, and only if the best strategy found was actually net
   profitable in that regime. Thinner or unprofitable regimes are left
   unassigned rather than guessed at.
3. On the following, unseen TEST window: at each bar, look up its regime
   (classified causally, so this doesn't use any information not available
   at that bar) and apply whichever strategy TRAIN assigned to that regime
   - or stay flat if nothing was assigned. The chosen signal is replayed
   through the exact same `run_backtest()` execution/cost/liquidation logic
   every other strategy uses, via a thin internal adapter
   (`_PrecomputedSignalStrategy`), so switching strategies mid-stream still
   pays real trading costs like any other position change.
4. Stitch each fold's test-period equity into one continuous out-of-sample
   curve, exactly like `walkforward.py` does for a single strategy.

The regime -> strategy mapping trained on *all* available data (not just one
fold) becomes the "live" recommendation shown on the dashboard: current
regime, and whichever strategy has the best confirmed edge in it right now.

**Stated limitation, not a footnote.** This runs on a genuinely small
dataset by ML standards - a few thousand bars, a handful of regime buckets,
a handful of assets - so a learned mapping like this is *easier* to overfit
than the simple rule-based strategies it's choosing between, not harder.
The `min_regime_bars` + profitability gate reduces that risk, it doesn't
eliminate it. Real, observed out-of-sample results across the six tracks
this has been run against so far range from +80.6% (BTC daily) to -84.9%
(ETH daily) - a genuinely honest spread, not cherry-picked, and a reminder
that "regime-aware" doesn't automatically mean "better." Treat every number
this produces with the same skepticism as any other walk-forward result.

Also not part of the hourly pipeline (same reasoning as walk-forward/
sensitivity below - it re-backtests every strategy per fold, expensive next
to a single backtest). Run manually:

```
python scripts/meta_strategy_snapshot.py --bars paper_trading/bars.csv --symbol BTC_USDT --freq 1D --output paper_trading/meta_strategy.json
```

## Robustness checks (not part of the hourly pipeline - run manually)

Two separate questions, both expensive (grid search per fold/parameter
value), so neither runs on every hourly update:

- `scripts/walkforward_snapshot.py` - re-optimizes each strategy's
  parameters on rolling training windows and scores it only on data it
  never saw during that fit (`walkforward*.json`). Answers "did this hold
  up on unseen data."
- `scripts/sensitivity_snapshot.py` - sweeps each strategy's parameter
  space one value at a time and reports what fraction of nearby values
  were also profitable (`sensitivity*.json`). Answers "is the edge a
  plateau, or a spike at exactly one setting."

Both scripts (plus `meta_strategy_snapshot.py`) accept `--leverage`, which
sets `capital_fraction` and swaps in the maintenance-margin-based
liquidation floor (`perp_max_loss_fraction()`, imported directly from
`paper_trade_update.py` rather than duplicated) instead of the flat
unleveraged floor - a flat floor is economically meaningless at leverage,
same reasoning as the live perp tracks. This closed a real gap: all four
perpetual futures tracks had **zero** walk-forward/sensitivity/meta-strategy
validation until this was added - their Locked-in Strategy and
Meta-strategy Selector panels were placeholder text despite the tracks
themselves running live for a full session. Real result, now that they're
actually validated: none of the four leveraged tracks currently has a
strategy that clears all three Locked-in Strategy bars (profitable,
walk-forward-robust, parameter-stable) at once - a stronger, more precise
version of the "leverage punishes drawdowns" finding below, not just an
in-sample observation anymore. The four daily/15-min/ETH/SOL spot
snapshots were also refreshed while at it - the previous ones predated the
three pattern-recognition strategies entirely, so they were structurally
incomplete, not just stale.

The dashboard's "Robustness (walk-forward)" table shows both together per
track, and the landing page's "Cross-asset validated" panel cross-
references walk-forward results across the three daily tracks (BTC/ETH/
SOL) - a strategy robust on all three independent price histories is much
harder to explain by luck than one that only worked on one.

## Other context surfaced on the dashboard

- **Regime** (`src/backtest/regime.py`, `compute_current_regimes()`) - each
  asset's latest ADX-based trend/volatility classification, shown as a
  pill on the landing page's asset cards. Trend-following strategies need
  a trending regime to have anything to catch.
- **Correlation** - pairwise Pearson correlation of daily returns across
  BTC/ETH/SOL, so ETH/SOL results can be checked for whether they're a
  genuinely independent signal or just BTC beta.
- **News** - recent crypto headlines from public RSS feeds, tagged by
  likely BTC/ETH/SOL/Regulation/ETF/Macro relevance. Context, not a
  trading signal - nothing here reads or reacts to it.

## Files

Per track (suffix `""` = BTC daily, `_15m`, `_eth`, `_sol`, `_perp`,
`_perp_15m`, `_eth_perp`, `_sol_perp`, `_nq`, `_nq5m`, `_es`, `_es5m`,
`_ym`, `_ym5m`, `_gc`, `_gc5m`):
`bars{suffix}.csv`, `positions{suffix}.json`, `trade_log{suffix}.csv`,
`track_record{suffix}.csv`, `summary{suffix}.md`,
`walkforward{suffix}.json`, `sensitivity{suffix}.json`, `meta_strategy{suffix}.json`
(the last three only where a manual snapshot has been run) - `bars_nq*.csv`,
`bars_es*.csv`, `bars_ym*.csv`, and `bars_gc*.csv` are fetched by
`scripts/fetch_index_futures.py` rather than `fetch_market_data.py` (see
"Index Futures" above). Plus `memecoin_scan.json` /
`memecoin_wide_scan.json` / `memecoins_wide_tickers.json` /
`memecoins/*.csv` (scanner), `rug_watch_history.json` (rolling ~7-day log
of flagged coins per hourly run, see "Rug Pull Watch" below),
`btc_market_snapshot.json` (order book + funding), `fear_greed.json`,
`news.json`, `index.html` + `dashboard.html` (built output - regenerate
with `python scripts/build_paper_trading_dashboard.py`, never hand-edit).

## Rug Pull Watch

A panel on the memecoin scanner tab (and a compact badge on the landing
page) flagging coins with a severe 24h decline or drawdown from their own
24h high - the price-action *aftermath* a rug pull leaves behind, not the
on-chain cause. Severity thresholds live in `scripts/rug_watch.py`, the one
shared source of truth between `memecoin_wide_scan.py` (which logs flagged
coins to `rug_watch_history.json` each hourly run) and
`build_paper_trading_dashboard.py` (which summarizes that history for the
landing page and computes each flagged coin's consecutive-run streak for
the full table - a persistent flag is a stronger signal than a one-off
dip). The full table on `dashboard.html` re-implements the same thresholds
in JS, since that page has no build step to share Python with.

The 24h check alone misses a coin that peaked a few days ago and has been
grinding down slowly since - no single day's change looks severe, even
though the cumulative slide is. For the 11 coins with full hourly history
(`memecoin_scan_update.py`'s precise scan, ~12 days of bars), the same
drawdown thresholds are also applied against each coin's trailing window
high (`severity_for_multiday_drawdown()`), not just its 24h high. A coin
flagged by both checks keeps the worse of the two severities; the table
tags each row with which check caught it ("24h" or "multi-day") so it's
clear why a coin showed up.

Honest caveat, worth repeating: this is a crash proxy from CEX ticker data
(24h change, volume) alone - there's no holder-concentration or liquidity-
lock signal available from this data source, and Crypto.com Exchange is a
curated, mainstream listing where an actual on-chain rug pull (LP drain,
honeypot contract) is rare. Most flags will be ordinary high-volatility
drawdowns or thin-liquidity air pockets, not literal rugs.

## Caveats

- **Simulated, not real money.** No trades are ever actually placed
  anywhere. Not investment advice.
- **Hourly, not real-time.** This checks in on the real market roughly
  once an hour; it does not react intraday except within that cadence.
- **Costs are modeled but simplified.** Crypto tracks use Crypto.com's
  published taker fee (0.075%) plus an assumed 0.05% slippage, both
  round-trip. Real fills, especially in thin memecoin markets, can be
  worse.
- **Most strategies are not currently profitable.** Read the walk-forward
  and sensitivity numbers before trusting any full-backtest headline
  return - see "Robustness checks" above. A strategy showing a large
  in-sample return can still be a curve-fit that fails on data it never
  saw.
