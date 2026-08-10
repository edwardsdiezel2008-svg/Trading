# Crypto paper trading cockpit

Simulated (no real money) live trading of 9 backtested strategies across 9
tracks - BTC (daily, 15-minute, 3x leveraged perpetual daily, 3x leveraged
perpetual 15-minute), ETH (daily, 3x leveraged perpetual), SOL (daily, 3x
leveraged perpetual), and Nasdaq-100 Futures (QQQ proxy, daily) - against
real Crypto.com Exchange and Stooq data, plus a wide memecoin momentum/
breakout scanner, updated hourly.

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
   `scripts/fetch_nasdaq_data.py` pulls QQQ daily bars from Stooq's free,
   keyless CSV endpoint (see "Nasdaq-100 Futures" below); and
   `scripts/fetch_news.py` pulls crypto headlines from public RSS feeds
   (CoinDesk, CoinTelegraph, Bitcoin.com).
2. `scripts/paper_trade_update.py` (once per track: BTC daily, BTC
   15-min, BTC Perpetual daily, BTC Perpetual 15-min, ETH, SOL, ETH
   Perpetual, SOL Perpetual, Nasdaq-100 Futures) re-runs the same tested
   backtest engine (`src/backtest/engine.py`) on the full bar history for every strategy
   and derives each one's current position from the last bar of a fresh,
   complete backtest - no separate incremental "live execution" logic that
   could drift out of sync with what the engine actually validated. Both
   15-minute tracks also pass `--cost-aware-min-multiple 1.0`, wrapping
   every strategy in `CostAwareFilter` (`src/backtest/strategies/cost_filter.py`)
   so it only trades when the recent ATR-based expected move can plausibly
   clear the round-trip transaction cost - reusing daily-tuned strategy
   periods unfiltered on 15-minute bars caused far more whipsaw trades than
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
daily, `_sol_perp` SOL daily) run the same 9 strategies against the same
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
equivalents: leverage doesn't just scale returns by a fixed multiple. As of
this writing, the ETH and SOL perpetual tracks show 0/9 profitable
strategies each, against 3/9 and 5/9 profitable on their unleveraged spot
equivalents - the same drawdowns that a spot position recovers from can
instead trigger a permanent liquidation at leverage, which compounds very
differently over dozens of trades. That's a real result of the simulation,
not a bug in it.

## Nasdaq-100 Futures

A ninth track (`_nq`) runs the same 9 strategies against **QQQ** (the
Invesco QQQ Trust), not real CME NQ/MNQ futures contracts. Three honest
caveats, all surfaced directly on the dashboard tab, not just here:

- **Why QQQ, not real futures data.** Genuine Nasdaq-100 futures tick/bar
  history isn't available from any free, no-API-key, no-CAPTCHA public
  source - every option checked (EODHD, Financial Modeling Prep, Databento,
  kibot, firstratedata) requires at least a free account, and this
  unattended hourly pipeline has no way to hold credentials for one. QQQ is
  the most liquid public proxy for the index, and Stooq
  (`https://stooq.com/q/d/l/?s=qqq.us&i=d`) serves its full daily history as
  a plain, keyless CSV - `scripts/fetch_nasdaq_data.py` fetches it the same
  way `fetch_market_data.py` fetches crypto candles, no auth required.
- **Why unleveraged.** Real Micro E-mini Nasdaq-100 (MNQ) futures currently
  require roughly $1,650 in CME initial margin against a notional value of
  tens of thousands of dollars - implied leverage in the ~25-30x range, set
  by the exchange itself, not a discretionary choice like the crypto
  perpetual tracks' 3x. This track deliberately does not attempt to
  simulate that: the backtest engine only checks for a liquidation-
  triggering loss at each bar's *close* (same limitation noted above for
  the perpetual tracks), and daily bars are far too coarse to responsibly
  model ~25-30x margin risk without either constant false liquidations or a
  liquidation threshold so loose it stops meaning anything. The track runs
  unleveraged instead (plain equity economics: $0 commission, matching most
  modern brokers' ETF trades, plus 0.05% slippage), so the real
  leverage/liquidation risk of actual futures trading is context here, not
  something simulated.
- **Why daily-only.** Stooq's per-symbol download only serves daily/weekly/
  monthly data without a key; true intraday data exists there but only via
  a CAPTCHA-gated bulk archive that can't be automated in an unattended
  pipeline. Real NQ/MNQ futures also trade nearly 24 hours a day, while QQQ
  only trades during exchange session hours - another reason intraday
  wouldn't be an honest proxy even if the data existed.

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
`_perp_15m`, `_eth_perp`, `_sol_perp`, `_nq`):
`bars{suffix}.csv`, `positions{suffix}.json`, `trade_log{suffix}.csv`,
`track_record{suffix}.csv`, `summary{suffix}.md`,
`walkforward{suffix}.json`, `sensitivity{suffix}.json` (the last two only
where a manual snapshot has been run) - `bars_nq.csv` is fetched by
`scripts/fetch_nasdaq_data.py` rather than `fetch_market_data.py` (see
"Nasdaq-100 Futures" above). Plus `memecoin_scan.json` /
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
