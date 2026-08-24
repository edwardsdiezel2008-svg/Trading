import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

import scripts.simulate_recent_period as simulate_recent_period
from src.backtest.strategies.base import Strategy


class AlwaysShort(Strategy):
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(-1, index=bars.index)


def test_simulated_return_freezes_rather_than_flips_sign_when_account_was_already_blown(tmp_path, monkeypatch):
    # A naked short blown deeply negative by a violent rally that happens
    # entirely BEFORE the requested window, then a partial recovery within
    # the window (price falling back some, so the account's real-dollar
    # equity actually improves during the window). Reproduces the same
    # class of bug already fixed in walkforward.py/meta_strategy.py: dividing
    # by a *negative* equity_at_window_start "succeeds" numerically but
    # flips the sign, reporting the window as a loss instead of the
    # recovery it actually was.
    seg1 = np.full(50, 100.0)
    seg2 = np.linspace(100, 100_000.0, 30)   # blows the short - entirely before the window
    seg3 = np.linspace(100_000, 90_000.0, 20)  # the window itself: price falls back, account improves
    prices = np.concatenate([seg1, seg2, seg3])
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="1D")
    bars = pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)

    csv_path = tmp_path / "bars.csv"
    bars.reset_index(names="timestamp").to_csv(csv_path, index=False)

    monkeypatch.setattr(simulate_recent_period, "ALL_STRATEGY_CLASSES", [AlwaysShort])

    table = simulate_recent_period.main([
        "--data", f"{csv_path}:TEST", "--freq", "1D", "--days", "20", "--capital", "100",
    ])

    row = table.iloc[0]
    # The account was already deeply negative before the window started -
    # no meaningful "simulated return" is derivable from that base, so the
    # multiple should freeze at 1.0 (unchanged), not report a fabricated
    # loss (or gain) from a sign-flipped division.
    assert row["final_CAD"] == 100.0
    assert row["return_pct"] == 0.0


def test_main_raises_systemexit_when_days_is_not_less_than_the_bar_count(tmp_path):
    import pytest

    prices = np.full(20, 100.0)
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="1D")
    bars = pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 100}, index=idx)
    csv_path = tmp_path / "bars.csv"
    bars.reset_index(names="timestamp").to_csv(csv_path, index=False)

    with pytest.raises(SystemExit, match="must be less than the available bar count"):
        simulate_recent_period.main(["--data", f"{csv_path}:TEST", "--freq", "1D", "--days", "20", "--capital", "100"])
