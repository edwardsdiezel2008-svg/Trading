"""Load raw tick logs (NASDAQ / futures) and resample them into OHLCV bars.

Strategies and the backtest engine operate on bars, not raw ticks - trying to
generate signals tick-by-tick is noisy and slow. Ticks are still used, though:
resampling to bars is where realistic volume and price-path information comes
from, and the same loader can be pointed at an already-bar-level CSV (e.g. a
file you exported pre-aggregated) and it will skip resampling.

Expected tick CSV columns (case-insensitive, flexible naming): a timestamp
column, a price column, and optionally a size/volume column. Common exchange
export headers are mapped automatically; anything else can be passed via
`column_map`.
"""
from __future__ import annotations

import pandas as pd

_TIMESTAMP_ALIASES = ["timestamp", "time", "datetime", "date_time", "ts"]
_PRICE_ALIASES = ["price", "last", "trade_price", "close"]
_SIZE_ALIASES = ["size", "volume", "qty", "quantity", "trade_size"]


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for alias in aliases:
        if alias in lower:
            return lower[alias]
    return None


def load_ticks(path: str, column_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Load a raw tick log into a DataFrame indexed by timestamp with columns
    ['price', 'size'].

    `column_map` overrides auto-detection, e.g. {"timestamp": "TradeTime", "price": "Px"}.
    """
    df = pd.read_csv(path)
    column_map = column_map or {}

    ts_col = column_map.get("timestamp") or _find_column(list(df.columns), _TIMESTAMP_ALIASES)
    price_col = column_map.get("price") or _find_column(list(df.columns), _PRICE_ALIASES)
    size_col = column_map.get("size") or _find_column(list(df.columns), _SIZE_ALIASES)

    if ts_col is None or price_col is None:
        raise ValueError(
            f"Could not identify timestamp/price columns in {path}. "
            f"Found columns: {list(df.columns)}. Pass column_map={{'timestamp': ..., 'price': ...}}."
        )

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df[ts_col]),
        "price": df[price_col].astype(float),
        "size": df[size_col].astype(float) if size_col else 1.0,
    })
    out = out.dropna(subset=["timestamp", "price"]).sort_values("timestamp")
    return out.set_index("timestamp")


def ticks_to_bars(ticks: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """Resample a tick DataFrame (from load_ticks) into OHLCV bars.

    freq uses pandas offset aliases: '1min', '5min', '1h', '1D', etc.
    Bars with no trades in the interval are dropped (no forward-filling -
    a flat-filled bar would fabricate zero-volatility periods that never happened).
    """
    price = ticks["price"].resample(freq)
    bars = pd.DataFrame({
        "open": price.first(),
        "high": price.max(),
        "low": price.min(),
        "close": price.last(),
        "volume": ticks["size"].resample(freq).sum(),
    })
    return bars.dropna(subset=["open", "high", "low", "close"])


_OHLCV_ALIASES = {
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c", "last"],
    "volume": ["volume", "vol", "size"],
}


def _looks_like_bars(columns: list[str]) -> bool:
    lower = {c.lower() for c in columns}
    return {"open", "high", "low", "close"}.issubset(lower)


def load_bars(path: str, freq: str = "1min", column_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Load a data file as OHLCV bars, auto-detecting whether it's already
    bar-level (has open/high/low/close columns) or raw tick data (needs
    resampling via `freq`).
    """
    df = pd.read_csv(path, nrows=5)
    if _looks_like_bars(list(df.columns)):
        full = pd.read_csv(path)
        column_map = column_map or {}
        ts_col = column_map.get("timestamp") or _find_column(list(full.columns), _TIMESTAMP_ALIASES)
        if ts_col is None:
            raise ValueError(f"Could not identify timestamp column in {path}. Columns: {list(full.columns)}")
        full["timestamp"] = pd.to_datetime(full[ts_col])
        full = full.set_index("timestamp").sort_index()

        renamed = {}
        for target, aliases in _OHLCV_ALIASES.items():
            col = column_map.get(target) or _find_column(list(full.columns), aliases)
            if col is None:
                if target == "volume":
                    full["volume"] = 0.0
                    continue
                raise ValueError(f"Missing required column '{target}' in {path}")
            renamed[col] = target
        full = full.rename(columns=renamed)
        # A NaN/blank OHLC value (a bad print from the upstream data source,
        # e.g. Yahoo Finance occasionally returning an empty field for a
        # given date) would otherwise load silently and poison the engine's
        # cumulative equity sum for the rest of the backtest - every bar
        # after it comes out NaN too, since equity is built via `+=`. The
        # tick-resampling path below already drops such rows; the bar-level
        # path needs the same guard.
        return full[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])

    ticks = load_ticks(path, column_map=column_map)
    return ticks_to_bars(ticks, freq=freq)
