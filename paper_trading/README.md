# Crypto + index futures paper trading cockpit

Simulated (no real money) live trading of 19 backtested strategies across 20
tracks - BTC (daily, 15-minute, 3x leveraged perpetual daily, 3x leveraged
perpetual 15-minute), ETH (daily, 3x leveraged perpetual), SOL (daily, 3x
leveraged perpetual), and real CME/COMEX/NYMEX futures across six markets -
Nasdaq-100 (NQ=F/MNQ), S&P 500 (ES=F/MES), Dow (YM=F/MYM), Russell 2000
(RTY=F/M2K), Gold (GC=F/MGC), and WTI Crude Oil (CL=F/MCL), each daily and
5-minute - against real Crypto.com Exchange and Yahoo Finance data, plus a
wide memecoin momentum/breakout scanner, updated hourly.

**Live site:** the root of this repo's GitHub Pages deployment is the
minimal landing page; `/dashboard.html` is the full detail page with every
track, chart, and table; `/learn.html` is a static methodology/glossary
page - what each strategy trades, how results get validated (walk-forward,
param stability, cross-asset robustness), and what every metric on the
dashboard means. `dashboard.html` is also installable as a home-screen app
on iPhone (Safari -> Share -> Add to Home Screen): a `manifest.json` +
`apple-touch-icon.png` give it a real icon and a standalone, no-address-bar
launch instead of a plain bookmark.

## How it actually works

There is no standalone bot process and no dependency on a Claude chat
session or MCP connector being open. `.github/workflows/hourly-market-data.yml`
runs on GitHub's own infrastructure every hour (`cron: "10 * * * *"`, plus
manual `workflow_dispatch`):

1. `scripts/fetch_market_data.py` - plain HTTP against Crypto.com Exchange's
   public REST API (no auth needed) for BTC/ETH/SOL candles, the wide
   memecoin ticker universe, BTC order book + perpetual funding rate;
   `scripts/fetch_index_futures.py` pulls real NQ=F, ES=F, YM=F, RTY=F,
   GC=F, and CL=F (CME Nasdaq-100, S&P 500, Dow, and Russell 2000 E-mini
   futures, plus COMEX Gold and NYMEX WTI Crude Oil) daily and 5-minute
   bars from Yahoo Finance's free, keyless chart endpoint (see "Index
   Futures" below); and `scripts/fetch_news.py` pulls crypto headlines
   from public RSS feeds (CoinDesk, CoinTelegraph, Bitcoin.com).
2. `scripts/paper_trade_update.py` (once per track: BTC daily, BTC
   15-min, BTC Perpetual daily, BTC Perpetual 15-min, ETH, SOL, ETH
   Perpetual, SOL Perpetual, Nasdaq/S&P 500/Dow/Russell 2000/Gold/Crude
   Oil Futures, each daily and 5-min)
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
for current counts, now across 19 strategies rather than the original 9) -
the same drawdowns that a spot position recovers from can instead trigger a
permanent liquidation at leverage, which compounds very differently over
dozens of trades. That's a real result of the simulation, not a bug in it.

## Index Futures

Twelve tracks (`_nq`/`_nq5m`, `_es`/`_es5m`, `_ym`/`_ym5m`, `_gc`/`_gc5m`,
`_rty`/`_rty5m`, `_cl`/`_cl5m`, each daily/5-min) run all 19 strategies
against **real futures prices** - CME's Nasdaq-100 E-mini (NQ=F), S&P 500
E-mini (ES=F), Dow E-mini (YM=F), and Russell 2000 E-mini (RTY=F), plus
COMEX Gold (GC=F) and NYMEX WTI Crude Oil (CL=F), all continuous front
contracts, fetched from Yahoo Finance's public `v8/finance/chart` endpoint
via the `yfinance` library (`scripts/fetch_index_futures.py`, generalized
from a Nasdaq-only script once the approach proved out live - see git
history). Each real futures price is paired with its Micro contract's
economics in `src/backtest/instruments.py`: **MNQ** ($2/index-point
multiplier, $0.75/side commission, 0.25-point tick), **MES** ($5/index-point
multiplier, $0.75/side commission, 0.25-point tick), **MYM** ($0.50/point
multiplier, $0.75/side commission, 1-point tick), **MGC** ($10/oz
multiplier, $0.75/side commission, 0.10-point tick), **M2K**
($5/index-point multiplier, $0.75/side commission, 0.10-point tick), and
**MCL** ($100/barrel-point multiplier, $0.75/side commission, 0.01-point
tick). The Micro contracts track the identical price level as their
full-size counterparts, just at a fraction of the contract size (1/10th in
every case here), so this is genuine futures point-value P&L math, not an
ETF-proxy approximation. (An earlier version of the Nasdaq track traded QQQ
as a proxy because Stooq's QQQ endpoint looked usable locally; a live run
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
  equity indices; M2K requires roughly $500-600 in maintenance margin
  against ~$11,000 typical notional (~18-22x); MCL requires roughly
  $500-600 in maintenance margin against ~$7,000 typical notional
  (~12-15x) - both smaller Micro contracts carry higher implied leverage
  since their dollar margin requirement doesn't shrink as fast as their
  notional does. All twelve tracks deliberately don't attempt to simulate
  any of these figures: the backtest engine only checks for a
  liquidation-triggering loss at each bar's *close* (same limitation noted
  above for the perpetual tracks), and modeling 10-30x real margin risk
  against bar-close-only checks - even on 5-minute bars - would produce
  either constant false liquidations or a threshold so loose it stops
  meaning anything. All twelve tracks run unleveraged instead (position
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
2022 rate-hike selloff), not an artifact. ES=F and GC=F check out equally
clean on the same structural tests (zero OHLC violations, ~251 trading
days/year); ES=F's >5% moves land on the same well-known dates as NQ=F's
(Feb 2018's "Volmageddon", the COVID crash, the 2025 tariff-selloff week),
which is expected since both track the same equity-market shocks. GC=F's
handful of >5% moves are plausible for a commodity but include dates past
this due-diligence pass's ability to independently corroborate against
known news (2025-10-21, 2026-01-30 to 2026-02-03) - flagged as unverified
rather than asserted. RTY=F checks out clean too (zero OHLC violations
across 2,287 bars, ~252 trading days/year; its >5% moves land on the same
dates as NQ=F/ES=F's during 2018/2020/2022/2025 shocks, plus a few small-cap-
specific ones like Nov 2020/2024 - both US election weeks, when Russell
2000 characteristically moves harder than the large-cap indices).

**Two real findings from this pass, reported as-is rather than smoothed
over:**

- **CL=F correctly captures the April 2020 negative-oil-price crash.**
  2020-04-20 closes at **-$37.63** and 2020-04-21 opens at **-$14.00** -
  the two `non-positive price` bars this due-diligence check flags for
  CL=F are the real WTI storage-capacity collapse (COVID demand crash
  colliding with near-zero remaining Cushing, Oklahoma storage capacity),
  not a data error - those are the actual historical settlement prices.
  The knock-on effect: CL=F's single-day-move check reports 133 moves
  over 5% (vs. ~15-20 for the equity index futures) - real WTI crude is
  simply far more volatile than an equity index at any point-value scale,
  and a handful of the extreme percentages right around April 20-21, 2020
  (some exceeding 100%) are a mathematical artifact of computing percent
  change across a price crossing through zero, not a sign of 133 separate
  anomalies. The live `_cl`/`_cl5m` paper-trading runs already process
  this event without crashing or producing NaN equity (confirmed from the
  first live hourly run's output) - P&L is driven by `multiplier *
  price_change`, a delta that doesn't care about the sign of the
  underlying price - but this hasn't been separately stress-tested per
  strategy, so it's flagged here rather than asserted as fully verified.
- **YM=F is not as clean as the other five.** 11 of 2,514 daily bars
  (0.4%) have `close > high` by 3-100 points - a genuine OHLC
  inconsistency, not present at all in NQ=F/ES=F/GC=F/RTY=F/CL=F's
  history. The violation dates don't cluster on quarterly
  futures-expiration weeks (they're scattered across 2024-2025, e.g.
  2024-08-01, 2024-10-30, 2025-02-26), which rules out the "rollover
  splice" explanation checked for above - this looks like a Yahoo
  data-vendor artifact specific to how YM=F's daily close gets
  aggregated, not a contract-splicing gap. Small in magnitude relative to
  Dow futures' typical daily range and rare enough (11 bars) that it's
  unlikely to meaningfully distort the walk-forward results already on
  file for `_ym`/`_ym5m`, but it's a real blemish in the source data and
  is reported here rather than silently ignored because it didn't break
  anything obvious.

The Nasdaq, S&P 500, Dow, and Gold Futures tracks all have real
walk-forward, sensitivity, and meta-strategy snapshots on file
(`walkforward_{nq,es,ym,gc}*.json` etc.) - the "🔒 Locked-in strategy" and
"🧠 Meta-strategy selector" panels are live there, not just placeholder
text. As of this writing: Nasdaq daily's locked-in pick is
`RSI_Reversion(14,30/70)` (+17.1% out-of-sample, Sharpe 0.77); Nasdaq
5-minute's is `Inside_Bar_Breakout(0.6)` (+6.1% OOS, Sharpe 1.44) - one of
the new pattern-recognition strategies added specifically for intraday
timeframes, and the only strategy that held up walk-forward-robust on the
5-minute track once ORB's session-boundary bug (below) was fixed. S&P 500
daily's locked-in pick is `RSI_Reversion(14,30/70)` (+6.6% out-of-sample,
Sharpe 0.71, 90% parameter-stable); S&P 500 5-minute's is
`ZScore_Reversion(20,z=2.0)` (+0.9% OOS, Sharpe 1.64, 86%
parameter-stable) - a different winner than Nasdaq's 5-minute track, a
useful cross-check that these aren't just picking the same strategy
everywhere regardless of the underlying instrument. Dow daily's locked-in
pick is `RSI_Reversion(14,30/70)` (+4.5% OOS, Sharpe 0.63, 90%
parameter-stable); Gold daily's is `MA_Crossover(10/50)` (+22.7% OOS,
Sharpe 0.56, 100% parameter-stable) - both 5-minute tracks currently have
no strategy clearing all three Locked-in Strategy bars. Russell 2000 daily's
locked-in pick is `VWAP_Reversion(20,2%)` (+2.8% OOS, Sharpe 0.22, 88%
parameter-stable); WTI Crude Oil daily's is `ZScore_Reversion(20,z=2.0)`
(+6.9% OOS, Sharpe 0.42, 100% parameter-stable) - both 5-minute tracks
currently have no strategy clearing all three bars either, continuing the
pattern that intraday futures tracks are harder to validate than daily
ones. Russell 2000 and WTI Crude Oil Futures were the most recent
additions, using the same proven pipeline - their real data landed and
these snapshots were run in the same round these instruments were added.

## Pattern-recognition strategies

Four of the 19 strategies read the raw shape of the candles rather than an
indicator series - added specifically because intraday timeframes (the
5-minute Nasdaq Futures track most of all) show far more of these setups
per session than a daily chart does. All four live in
`src/backtest/strategies/patterns.py`; the first three are standard,
publicly documented setups, not something invented for this project:

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
- **ORB ATR Target** - the same opening-range breakout entry, but with a
  defined risk:reward instead of holding until session end: stop-loss at
  a multiple of ATR from entry, target at the prior session's high (long)
  or low (short). Skips a breakout that's already blown past that target
  with no room left to run.

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

## Statistical significance (bootstrap confidence intervals)

A walk-forward OOS number is still a single point estimate from one
specific sequence of market history - "positive OOS return and positive OOS
Sharpe" (the bar every other check in this project uses for "robust") says
nothing about how confident that point estimate actually is. `src/backtest/
significance.py`'s `bootstrap_return_ci()` closes that gap: circular block
bootstrap resampling (1,000 resamples, 20-bar blocks to preserve the OOS
return series' own serial correlation rather than assuming i.i.d. bars) of
each strategy's walk-forward OOS equity curve, producing a 90% confidence
interval on total return. If that interval still includes zero, the result
can't be told apart from a strategy with no real edge at this sample size -
even when the point estimate itself is positive. Not a rigorous hypothesis
test (multiple testing across 19 strategies per track isn't corrected for),
just an honest uncertainty band a bare point estimate doesn't carry.

Wired into `walkforward_snapshot.py` - every `walkforward*.json` now carries
`oos_return_ci_low` / `oos_return_ci_high` / `oos_significant` per strategy
alongside the existing OOS metrics, no separate script to run. The dashboard
surfaces it two ways: a "90% CI (Bootstrap)" column in the Robustness
(walk-forward) table (green when the interval excludes zero, tooltip
explains why), and an explicit caveat sentence on the Locked-in Strategy
panel whenever the current pick's interval still includes zero - the pick
itself doesn't change (it still clears the plain profitable/robust/stable
bars), but the caveat makes the added uncertainty impossible to miss.

**The real result, run across every one of the 20 walkforward snapshots
(380 strategy-track combinations total, 19 strategies x 20 tracks), is
sobering and reported in full rather than softened:** 112 of those 380
(29.5%) clear the plain "robust" bar (positive OOS return and positive
OOS Sharpe). Only **11** (2.9%) also have a 90% confidence interval that
excludes zero - statistically distinguishable from no real edge at all,
given how much data actually went into each estimate. Those eleven:

- `ATR_Vol_Breakout(14,k=1.5)` on BTC Perp 15-min: +56.5% OOS, 90% CI [+3.8%, +143.4%]
- `Donchian_Breakout(20)` on Gold daily: +25.4% OOS, 90% CI [+4.1%, +50.8%]
- `MA_Crossover(10/50)` on Gold daily: +22.5% OOS, 90% CI [+1.7%, +50.3%]
- `ATR_Vol_Breakout(14,k=1.5)` on BTC 15-min: +19.2% OOS, 90% CI [+2.3%, +40.6%]
- `RSI_Reversion(14,30/70)` on Nasdaq daily: +17.1% OOS, 90% CI [+7.0%, +28.0%]
- `RSI_Reversion(14,30/70)` on S&P 500 daily: +6.6% OOS, 90% CI [+0.8%, +13.9%]
- `Stochastic_Reversion(14,20/80)` on Nasdaq 5-min: +5.5% OOS, 90% CI [+0.8%, +10.3%]
- `CCI_Reversion(20,100)` on Crude Oil daily: +5.2% OOS, 90% CI [+0.8%, +10.4%]
- `ORB_ATR_Target(6,1.5xATR)` on Gold 5-min: +4.9% OOS, 90% CI [+1.3%, +8.7%]
- `RSI_Reversion(14,30/70)` on Dow daily: +4.5% OOS, 90% CI [+0.3%, +10.2%]
- `CCI_Reversion(20,100)` on Dow daily: +3.7% OOS, 90% CI [+0.2%, +7.2%]

Seven of the eleven are daily tracks, two are 15-minute, and two are
5-minute. The two 15-minute results - `ATR_Vol_Breakout` on both spot BTC
and 3x-leveraged BTC Perp - are the first crypto/perpetual results to
clear this bar; every prior run of this analysis had none. `RSI_Reversion`
shows up 3 of the 11 times, on three independent equity-index futures -
the same instrument-family consistency the "Cross-futures validated"
panel already surfaces, now with actual statistical backing behind it
rather than just a plain positive-Sharpe count. This doesn't mean the
other 101 "robust" results are worthless - a real edge can still exist
below what this sample size can statistically confirm - but it does mean
roughly 9 out of 10 walk-forward "robust" verdicts on this dashboard,
taken alone, are not yet distinguishable from noise. That is exactly the
honest answer to "what's actually profitable" this feature was built to
surface.

## Survivor stress test

Clearing the bootstrap significance bar is necessary, not sufficient, for
real confidence - a single significant walk-forward result could still be
one lucky fold, an edge thin enough that slightly worse execution erases
it, or a P&L concentrated in one narrow market condition that might not
recur. `scripts/survivor_stress_test.py` runs three more checks against
each of the 10 significant survivors, none of which the walk-forward
snapshot alone answers:

1. **Fold-by-fold consistency** - re-reads the same 5-fold walk-forward
   split and reports whether each individual fold's test-period return was
   positive, not just the stitched aggregate. A strategy positive in 5/5
   folds is a broader, more consistent edge than one carried by a single
   strong fold.
2. **Cost stress test** - re-runs the full walk-forward (fresh grid search
   included) at 3x the normal slippage assumption (`slippage_ticks=3.0`
   instead of the default 1.0). If the bootstrap CI no longer excludes
   zero under those tougher assumptions, the edge was thin enough that
   realistic execution friction alone could erase it.
3. **Regime concentration** - `src/backtest/regime.py`'s
   `attribute_performance()` on the full-history default-params backtest,
   reporting what share of total P&L came from the single largest regime
   bucket. A profit concentrated almost entirely in one regime is a
   narrower bet than one spread across conditions.

**Real results** (`paper_trading/survivor_stress_test.json`), reported as-is:

| Strategy | Track | Folds Positive | 3x-Cost Stress | Top Regime Share |
|---|---|---|---|---|
| RSI_Reversion(14,30/70) | Nasdaq daily | 5/5 | ✓ holds | 69.3% (trending/high_vol) |
| RSI_Reversion(14,30/70) | S&P 500 daily | 4/5 | ✓ holds | 86.2% |
| RSI_Reversion(14,30/70) | Dow daily | 3/5 | ✓ holds | 80.0% |
| MA_Crossover(10/50) | Gold daily | 4/5 | ✓ holds | 61.0% |
| Donchian_Breakout(20) | Gold daily | 4/5 | ✓ holds | 64.6% |
| CCI_Reversion(20,100) | Crude Oil daily | 5/5 | ✓ holds | 37.2% |
| CCI_Reversion(20,100) | Dow daily | 5/5 | **✗ fails** | 31.0% |
| Stochastic_Reversion(14,20/80) | Nasdaq 5-min | 4/5 | ✓ holds | 32.0% |
| Stochastic_Reversion(14,20/80) | Russell 2000 5-min | 5/5 | **✗ fails** | 39.5% |
| VWAP_Reversion(20,2%) | Gold 5-min | 3/5 | ✓ holds | n/a (regime attribution not run at this bar frequency) |

**Nasdaq's `RSI_Reversion` is the strongest of the ten** - positive in
every one of the 5 independent fold periods, and its edge survives tripling
the slippage assumption with the point estimate barely moving (17.1% ->
17.0% OOS). **Two results are the real caution flags here**: Dow's
`CCI_Reversion` and Russell 2000's `Stochastic_Reversion` both flip to
including zero once slippage triples, meaning their significance is fragile
enough that a small, entirely plausible change in execution-cost
assumptions erases it - despite both being positive in 5/5 folds, which by
itself would otherwise read as a strong result. Fold consistency and cost
robustness are answering different questions, and a survivor can pass one
and fail the other. Most of the ten show meaningful regime concentration
(31-86% of P&L from one bucket), which isn't disqualifying on its own -
most real trading edges are regime-dependent by nature - but it does mean
each of these should be read as "works well in [that regime]," not "works
everywhere." Surfaced on the landing page's "Survivor stress test" panel,
sourced from the same JSON.

**Portfolio combination.** None of the checks above answer a different,
natural next question: does combining survivors into a single equal-weighted
portfolio actually diversify anything, or are they all just riding the same
underlying factor? `portfolio_analysis()` only combines survivors that
share a bar frequency - daily and 5-minute OOS equity curves have no
common timestamps, so naively intersecting them would produce an empty,
meaningless alignment. The seven daily survivors form the only group large
enough to be worth combining; the three 5-minute survivors (Nasdaq and
Russell 2000 Stochastic, Gold VWAP) are excluded from this step for that
reason, not because they're weaker. `portfolio_analysis()` aligns the seven
daily OOS equity curves on their common date intersection (2018-04-17 to
2026-08-17, 2,098 trading days) and bootstraps a confidence interval on the
equal-weighted combination exactly like each individual survivor was
checked.

**Real result: yes, genuinely, though less dramatically than with the
original five.** Mean pairwise daily-return correlation across the seven is
just 0.227 - but that low average hides real structure, not seven
independent bets. The correlation matrix splits into three clusters: the
two Gold strategies correlate at 0.90 with each other (same instrument,
both trend-following), the three equity-index `RSI_Reversion` /
`CCI_Reversion` names correlate at 0.42-0.95 with each other (same macro
risk factor, and Dow's `CCI_Reversion` rides that same factor even though
it's a different indicator), while Crude Oil's `CCI_Reversion` sits at
essentially zero correlation with everything else (0.01-0.06). Combining
all seven at equal weight over the same aligned window produces a total
return of +11.7% (vs. +11.8% average of the seven individually - close,
since Gold's two strong performers are offset by the three more modest
equity-index/Crude legs) but a meaningfully higher Sharpe ratio - 0.93 for
the portfolio vs. 0.62 average for the seven taken separately, still
comfortably statistically significant (90% CI [+5.1%, +19.0%], excludes
zero). That's the textbook diversification benefit, earned honestly from
combining one uncorrelated commodity edge (Crude Oil) with a correlated
equity-index cluster and a correlated Gold pair - not from seven genuinely
independent signals, which the correlation matrix makes clear is not what's
actually happening here.

## Robustness checks (not part of the hourly pipeline - run manually)

Two separate questions, both expensive (grid search per fold/parameter
value), so neither runs on every hourly update:

- `scripts/walkforward_snapshot.py` - re-optimizes each strategy's
  parameters on rolling training windows and scores it only on data it
  never saw during that fit (`walkforward*.json`). Answers "did this hold
  up on unseen data." Also runs the bootstrap significance check above on
  the resulting OOS equity curve.
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
track, and the landing page has two cross-referencing panels built on the
same `_cross_track_robustness()` helper in `build_paper_trading_dashboard.py`:
"Cross-asset validated" checks the three crypto daily tracks (BTC/ETH/SOL),
and "Cross-futures validated" checks all six daily futures tracks
(NQ/ES/YM/RTY/GC/CL) - a strategy robust on several independent price
histories at once is much harder to explain by luck than one that only
worked on a single instrument. Real result from the futures side, as of
this writing: `RSI_Reversion(14,30/70)` and `ZScore_Reversion(20,z=2.0)`
are walk-forward-robust on 5 of the 6 futures markets (everything except
Gold) - the strongest cross-market signal in either panel right now, and a
genuinely useful answer to "which strategy should I actually trust" beyond
any single instrument's Locked-in Strategy pick.

## Backtest Lab

A separate page (`paper_trading/backtest_lab.html`) for a question none of
the tables above answer directly: given a real starting balance and a real
drawdown limit, would a specific strategy's actual historical run have
survived it? Built by `scripts/build_backtest_lab.py`, which backtests each
of the 19 strategies against its own `PARAM_SPACE`'s full, real, documented
parameter grid - not samples, not invented values - capped at 50
combinations per strategy (an evenly-spaced thinning of the real grid only
kicks in if a strategy's grid actually exceeds that; today the largest,
RSIReversion, has 36), against all seven tracks this project fetches at 1-5
minute resolution (NQ 1-min; NQ/ES/YM/RTY/GC/CL 5-min - there is no other
genuine intraday bar data available). That's roughly 1,650-1,850 real
backtests per run depending on how many configs each strategy resolves to
after deduping combos that land on the same effective parameters.

A **Leaderboard** tab ranks every one of those backtests - filterable by
track and strategy, sortable by total return, Sharpe, profit factor, or win
rate - so you can see which strategy and parameter combination actually
performed best instead of picking one blind. Only compact real data ships
to the page: each track's bars as `[epoch_seconds, close]`, every config's
summary metrics for the leaderboard, and - because shipping a full trade
list for every one of ~1,700 configs would balloon the page for combos
nobody will look at - full trade lists
(`[entry_idx, exit_idx, direction, entry_price, exit_price, net_pnl]`
tuples) only for the chart-worthy subset: each strategy's hardcoded
defaults and `PARAM_SPACE` extremes, plus whichever configs land in the top
10 by total return or top 10 by Sharpe on a given track. The page
reconstructs the full bar-level equity curve and simulates a trailing
(intraday or end-of-day) or static drawdown-limit breach entirely with
client-side arithmetic over those real numbers - no strategy logic is
duplicated in JavaScript, so the two can't drift apart. Wired into the
hourly workflow (skipped gracefully if the 1-5min bar files aren't seeded
yet) so it stays live like everything else.

None of the configurations here are claimed as validated - see "Statistical
significance" above before trusting any single result. The point of this
page is honest position sizing against a real risk budget, not a new
source of "this strategy works" claims.

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
`_ym`, `_ym5m`, `_gc`, `_gc5m`, `_rty`, `_rty5m`, `_cl`, `_cl5m`):
`bars{suffix}.csv`, `positions{suffix}.json`, `trade_log{suffix}.csv`,
`track_record{suffix}.csv`, `summary{suffix}.md`,
`walkforward{suffix}.json`, `sensitivity{suffix}.json`, `meta_strategy{suffix}.json`
(the last three only where a manual snapshot has been run) - `bars_nq*.csv`,
`bars_es*.csv`, `bars_ym*.csv`, `bars_gc*.csv`, `bars_rty*.csv`, and
`bars_cl*.csv` are fetched by `scripts/fetch_index_futures.py` rather than
`fetch_market_data.py` (see "Index Futures" above). Plus `memecoin_scan.json` /
`memecoin_wide_scan.json` / `memecoins_wide_tickers.json` /
`memecoins/*.csv` (scanner), `rug_watch_history.json` (rolling ~7-day log
of flagged coins per hourly run, see "Rug Pull Watch" below),
`btc_market_snapshot.json` (order book + funding), `fear_greed.json`,
`news.json` (fetched by `scripts/fetch_news.py`), `backtest_lab.json`
(built by `scripts/build_backtest_lab.py`, see "Backtest Lab" above).
`index.html`, `dashboard.html`, `news.html`, and `backtest_lab.html` are
all built output - regenerate with `python
scripts/build_paper_trading_dashboard.py`, never hand-edit (their
`*_template.html` sources are the ones to actually change).
`dashboard.html` and `backtest_lab.json` are gitignored despite being real,
needed files (present on disk, staged for Pages from the freshly-built
copy every run) - at ~35MB and ~13MB, rebuilt almost entirely differently
each hour, committing them was the single largest driver of this repo's
`.git` size. Run the build scripts locally to get local copies; don't
expect them in a fresh clone.

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
