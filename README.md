# Trading

A backtesting toolkit that runs a library of common trading techniques against
downloaded NASDAQ and futures trading logs, scores each one, and explains
*why* it performed the way it did (which market regime the profit/loss came
from), not just whether it did.

## What's here

```
src/backtest/
  data_loader.py     Load raw tick logs -> normalized OHLCV bars
  instruments.py      Contract specs (multiplier, tick size) for futures + equities
  strategies/          7 strategies: trend, mean-reversion, volatility
  engine.py            Backtest engine (next-bar execution, commissions, slippage)
  metrics.py           CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor...
  regime.py            Classifies bars as trending/ranging x high/low-vol, attributes P&L to each
  report.py            Runs everything, writes metrics.csv / equity_curves.png / explanations.txt
  walkforward.py        Walk-forward validation: grid-search params per fold, test out-of-sample
  sensitivity.py         Parameter sensitivity sweeps: is the edge a plateau or a lucky spike?
  cli.py                Command-line entry point
scripts/generate_sample_data.py   Synthetic tick data for testing the pipeline (NOT real market data)
scripts/run_validation.py         Runs walk-forward + sensitivity across the whole strategy library
tests/                 pytest suite
```

## Setup

```bash
pip install -r requirements.txt
```

## Quickstart with synthetic data

Before you've downloaded real logs, sanity-check the whole pipeline against a
generated dataset:

```bash
python scripts/generate_sample_data.py
python -m src.backtest.cli --data data/sample/NASDAQ_AAPL_ticks.csv:AAPL data/sample/ES_ticks.csv:ES --freq 5min
```

This prints a metrics table and writes `reports/metrics.csv`,
`reports/equity_curves.png`, and `reports/explanations.txt`.

## Fetching real data from Alpaca (free)

`scripts/fetch_alpaca_data.py` pulls historical bars from Alpaca's free IEX
feed and writes them straight into `data/raw/` in the format `load_bars()`
already auto-detects - no reformatting needed. Requires a free account and
API keys set as environment variables (never on the command line):

```bash
export ALPACA_API_KEY=...
export ALPACA_SECRET_KEY=...
python scripts/fetch_alpaca_data.py --symbols AAPL MSFT --start 2024-01-01 --end 2025-01-01 --timeframe 1Min
python -m src.backtest.cli --data data/raw/AAPL_1Min_bars.csv:AAPL --freq 1min
```

The free tier is the IEX feed (one exchange's volume, not the full
consolidated tape) - fine for backtesting, just not literally every NASDAQ
print. `--feed sip` gets the full tape but needs a paid subscription.

## Using your own downloaded logs

1. Drop tick log CSVs into `data/raw/` (gitignored - trading data is often
   large and/or licensed, so it's never committed).
2. Each file needs at minimum a timestamp column and a price column (size/volume
   is optional). Common header names are auto-detected
   (`timestamp`/`time`/`datetime`, `price`/`last`, `size`/`volume`/`qty`). If
   your export uses different headers, pass a `column_map` when calling
   `load_ticks`/`load_bars` directly, or rename the columns before loading.
3. Run:

```bash
python -m src.backtest.cli \
  --data data/raw/AAPL_ticks.csv:AAPL data/raw/ES_ticks.csv:ES \
  --freq 1min \
  --capital 100000
```

`SYMBOL` after the `:` matters - it's used to look up the instrument's
contract multiplier and tick size in `src/backtest/instruments.py` (ES, MES,
NQ, MNQ, YM, RTY, CL, GC are predefined; anything else defaults to a
multiplier of 1, i.e. treated as an equity). **Add real specs for any futures
symbol you use that isn't already listed, or P&L will be wrong.**

## The strategies

| Category | Strategy | Idea |
|---|---|---|
| Trend | `MovingAverageCrossover` | Long when fast MA > slow MA |
| Trend | `DonchianBreakout` | Long/short on new N-bar high/low (turtle-style) |
| Trend | `MACDMomentum` | Trade the sign of the MACD histogram |
| Mean reversion | `RSIReversion` | Long oversold (RSI<30), short overbought (RSI>70) |
| Mean reversion | `BollingerReversion` | Fade closes outside the Bollinger Bands back to the mean |
| Mean reversion | `ZScoreReversion` | Fade price >2 std devs from its rolling mean |
| Volatility | `ATRVolatilityBreakout` | Trade moves that exceed k*ATR (volatility expansion) |

Add a new one by subclassing `src/backtest/strategies/base.py:Strategy` and
implementing `generate_signals(bars) -> Series[-1, 0, 1]`, then adding it to
`ALL_STRATEGY_CLASSES` in `strategies/__init__.py`.

## How execution is modeled

- A signal computed from bar *t*'s close is only acted on starting at the
  **open of bar t+1** - no lookahead.
- Equity is marked to market every bar (open-to-close and the overnight/gap
  move), so drawdown reflects unrealized moves too, not just closed trades.
- Commission + slippage (in ticks) are charged on both entry and exit.
- Position sizing is either `fixed_units` (constant N shares/contracts - the
  default for futures) or `percent_equity` (notional-based, the default for
  equities). **Futures margin is not modeled** - `percent_equity` sizing for
  futures uses full notional value, which will oversize positions relative to
  what your actual margin allows. Use `fixed_units` for anything margin-based.

## Why regime attribution matters

A Sharpe ratio tells you a strategy worked; it doesn't tell you why. `regime.py`
classifies every bar by trend strength (ADX) and relative volatility, then
buckets each strategy's realized P&L by regime. `explanations.txt` (and the
`attribute_performance()` function) will tell you things like "this MA
crossover made 90% of its money in trending/low-vol conditions and lost money
the rest of the time" - which is what you need to know before trusting a
backtest to generalize, since it tells you the strategy is regime-dependent
rather than universally "profitable."

## Validating results: walk-forward + parameter sensitivity

`report.py` / `cli.py` are in-sample - the strategy sees the whole dataset
before you evaluate it, which is exactly the setup that makes overfitting
look like alpha. Two tools address that, and are run separately from the main
CLI because they're much more expensive (grid search, not a single backtest):

```bash
python scripts/run_validation.py --data data/sample/NASDAQ_AAPL_ticks.csv:AAPL --freq 5min --n-folds 5
```

- **Walk-forward validation** (`walkforward.py`): splits the data into
  expanding train / held-out test folds, grid-searches each strategy's
  `PARAM_SPACE` on the train slice only, and applies the winning parameters
  to the untouched test slice. The test folds are stitched into one
  continuous out-of-sample equity curve - that's the honest performance
  estimate, not the in-sample number. It's also compared against just running
  the strategy's fixed textbook defaults over the same out-of-sample window
  (`vs_fixed_default_ratio`), which answers "was re-optimizing even worth
  it?" separately from "does this strategy work out-of-sample at all?"
- **Parameter sensitivity** (`sensitivity.py`): sweeps each parameter
  individually around its default, holding the others fixed, and reports
  whether performance is a robust plateau (profitable across nearby values)
  or a lucky spike (great at exactly one setting, falls apart next to it).
  A spike is a strong overfitting signal even if the in-sample Sharpe looks
  great.

Output goes to `reports/validation/` (`walkforward_summary.csv`,
`walkforward_folds.csv`, `sensitivity_summary.csv`, `sensitivity_detail.csv`).

## Known limitations (read before trusting results)

- **CAGR/Calmar are suppressed (`NaN`) for backtests spanning under ~1
  month** - annualizing a few days of data compounds noise into meaningless
  numbers. `total_return` is always exact regardless of span; trust that for
  short backtests.
- Walk-forward validation exists (see above) but isn't run automatically -
  `report.py`/`cli.py` results are still in-sample unless you separately run
  `scripts/run_validation.py`. Promising in-sample results should always be
  checked out-of-sample before being trusted.
- No margin modeling for futures (see above).
- Strategy parameters default to textbook values; `PARAM_SPACE` on each
  strategy class defines a small grid for walk-forward/sensitivity, but it's
  a starting point, not an exhaustive search.

## Tests

```bash
python -m pytest tests/ -q
```

## Daily journal + live calendar planner

`journal/` keeps a dated folder per day of work on this project (tasks +
notes), browsable as a live monthly calendar:

```bash
python scripts/journal.py new                  # scaffold today's folder
python scripts/journal.py task "did the thing" --done
python scripts/journal.py serve                 # live calendar at journal/calendar.html
```

See `journal/README.md` for the full workflow.
