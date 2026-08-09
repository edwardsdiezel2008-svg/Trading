import pandas as pd
import pytest

from src.backtest.engine import run_backtest
from src.backtest.instruments import InstrumentSpec
from src.backtest.strategies.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=bars.index)


class AlwaysFlat(Strategy):
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(0, index=bars.index)


class FlipAtBar(Strategy):
    """Long for bars before `flip_at`, short from `flip_at` onward."""
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        flip_at = self.params["flip_at"]
        n = len(bars)
        return pd.Series([1 if i < flip_at else -1 for i in range(n)], index=bars.index)


class LongUntil(Strategy):
    """Long for bars before `flip_at`, flat from `flip_at` onward."""
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        flip_at = self.params["flip_at"]
        n = len(bars)
        return pd.Series([1 if i < flip_at else 0 for i in range(n)], index=bars.index)


def _flat_spec(multiplier=1.0, commission=0.0, tick_size=0.01):
    return InstrumentSpec("TEST", "equity", multiplier=multiplier, tick_size=tick_size, commission_per_unit=commission)


def _bars(prices, opens=None):
    idx = pd.date_range("2026-01-05", periods=len(prices), freq="1min")
    opens = opens if opens is not None else prices
    return pd.DataFrame({"open": opens, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)


def test_flat_strategy_never_trades_and_preserves_capital():
    bars = _bars([100, 101, 99, 102, 98])
    spec = _flat_spec()
    result = run_backtest(bars, AlwaysFlat(), spec, initial_capital=10_000, capital_fraction=1.0, slippage_ticks=0)
    assert result.trades == []
    assert (result.equity_curve == 10_000).all()


def test_long_only_strategy_no_lookahead_first_bar_flat():
    # Signal is computed at close(t) and only acted on starting open(t+1), so the
    # very first bar must show zero position (nothing to react to yet).
    bars = _bars([100, 100, 100, 100])
    spec = _flat_spec(commission=0.0)
    result = run_backtest(bars, AlwaysLong(), spec, initial_capital=10_000, sizing="fixed_units", fixed_units=1, slippage_ticks=0)
    assert result.positions.iloc[0] == 0
    assert result.positions.iloc[1] == 1


def test_pnl_matches_price_times_units_for_a_simple_long(monkeypatch=None):
    # Flat price except a jump from 100 -> 110 after entry; with 1 fixed unit
    # and multiplier=1, entering long should capture that $10 move exactly
    # (minus zero commission/slippage here).
    prices = [100, 100, 100, 110, 110]
    bars = _bars(prices)
    spec = _flat_spec(commission=0.0, tick_size=0.01)
    result = run_backtest(bars, AlwaysLong(), spec, initial_capital=10_000, sizing="fixed_units", fixed_units=1, slippage_ticks=0)
    assert result.equity_curve.iloc[-1] == pytest.approx(10_000 + 10.0)


def test_commission_and_slippage_reduce_pnl():
    prices = [100, 100, 100, 110, 110]
    bars = _bars(prices)
    spec = _flat_spec(commission=1.0, tick_size=0.5)
    result = run_backtest(bars, AlwaysLong(), spec, initial_capital=10_000, sizing="fixed_units", fixed_units=1, slippage_ticks=2)
    # entry cost = 1 unit * (1.0 commission + 2 ticks * 0.5) = 2.0; no exit (position held to the end, closed at final close)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.gross_pnl == pytest.approx(10.0)
    assert trade.costs == pytest.approx(4.0)  # entry (2.0) + exit (2.0)
    assert trade.net_pnl == pytest.approx(6.0)


def test_flip_produces_two_trades():
    prices = [100] * 10
    bars = _bars(prices)
    spec = _flat_spec()
    result = run_backtest(bars, FlipAtBar(params={"flip_at": 5}), spec, initial_capital=10_000, sizing="fixed_units", fixed_units=1, slippage_ticks=0)
    assert len(result.trades) == 2
    assert result.trades[0].direction == 1
    assert result.trades[1].direction == -1


def test_percent_equity_sizing_scales_with_capital():
    bars = _bars([100] * 5)
    spec = _flat_spec()
    result = run_backtest(bars, AlwaysLong(), spec, initial_capital=1_000, sizing="percent_equity", capital_fraction=0.5)
    # 0.5 * 1000 / 100 = 5 units
    assert result.trades[0].units == pytest.approx(5.0)


def test_percent_equity_sizing_floors_to_whole_units_for_non_fractional_assets():
    # $100 equity against a $65 price: 100/65 = 1.53 units, but stocks/futures
    # can't hold a fractional share/contract, so this must floor to 1.
    bars = _bars([65] * 3)
    spec = _flat_spec()  # fractional_units defaults to False
    result = run_backtest(bars, AlwaysLong(), spec, initial_capital=100, sizing="percent_equity")
    assert result.trades[0].units == pytest.approx(1.0)


def test_percent_equity_sizing_stays_fractional_for_crypto_style_assets():
    # Same $100 against a $65,000 price (BTC-scale): flooring would zero out
    # the position entirely, which is exactly the bug this test guards against.
    bars = _bars([65_000] * 3)
    spec = InstrumentSpec("BTC_USDT", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True)
    result = run_backtest(bars, AlwaysLong(), spec, initial_capital=100, sizing="percent_equity")
    assert len(result.trades) == 1
    assert result.trades[0].units == pytest.approx(100 / 65_000)


def test_max_loss_fraction_force_closes_before_the_strategy_would_exit():
    # Long entered at 100 with 100% of equity; crashes to 40 (a 60% loss) on
    # bar 2, then the strategy itself would only go flat on bar 3. Without a
    # floor, equity rides the crash out to whatever the position is worth
    # when the signal eventually exits (or the backtest ends) - no ceiling
    # on the drawdown. With max_loss_fraction=0.5, the position must be
    # force-closed the moment the 60% loss is realized (bar 2's close), one
    # bar earlier than the strategy's own flat signal (bar 3's open).
    closes = [100, 100, 40, 10]
    opens = [100, 100, 100, 40]
    bars = _bars(closes, opens=opens)
    spec = _flat_spec()
    strat = LongUntil(params={"flip_at": 2})

    capped = run_backtest(bars, strat, spec, initial_capital=10_000, sizing="percent_equity", slippage_ticks=0, max_loss_fraction=0.5)
    uncapped = run_backtest(bars, strat, spec, initial_capital=10_000, sizing="percent_equity", slippage_ticks=0)

    assert len(capped.trades) == 1
    assert capped.trades[0].exit_time == bars.index[2]  # stopped out mid-backtest
    assert capped.positions.iloc[2] == 0  # flat immediately after the forced close
    assert capped.equity_curve.iloc[-1] == pytest.approx(4_000.0)

    assert len(uncapped.trades) == 1
    assert uncapped.trades[0].exit_time == bars.index[3]  # only exits when the signal goes flat
    # Same price path, so the loss is identical in dollar terms either way -
    # the fix changes *when* the position is closed, not the crash itself.
    assert uncapped.equity_curve.iloc[-1] == pytest.approx(4_000.0)


def test_max_loss_fraction_off_by_default():
    # Default behavior (max_loss_fraction=None) must be byte-for-byte
    # unchanged from before the parameter existed - every other track's
    # already-generated backtest numbers depend on this.
    bars = _bars([100, 100, 40, 10], opens=[100, 100, 100, 40])
    spec = _flat_spec()
    strat = LongUntil(params={"flip_at": 2})
    with_explicit_none = run_backtest(bars, strat, spec, initial_capital=10_000, sizing="percent_equity", slippage_ticks=0, max_loss_fraction=None)
    without_param = run_backtest(bars, strat, spec, initial_capital=10_000, sizing="percent_equity", slippage_ticks=0)
    assert with_explicit_none.equity_curve.tolist() == without_param.equity_curve.tolist()
    assert len(with_explicit_none.trades) == len(without_param.trades) == 1
