"""Instrument specifications: contract multipliers, tick sizes, and asset class.

Equities (NASDAQ etc.) default to multiplier=1 (1 share = 1 point of P&L per $1 move).
Futures need a real point multiplier or P&L will be wrong by orders of magnitude.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    asset_class: str  # "equity" or "future"
    multiplier: float  # $ P&L per 1.0 price move, per contract/share
    tick_size: float  # minimum price increment
    commission_per_unit: float  # $ per share or per contract, one side


# Common defaults. Override/add via YAML config passed to the CLI for anything not listed.
DEFAULT_SPECS = {
    # Equities - NASDAQ listed, multiplier 1, commission assumed ~0 (many brokers are free)
    "_default_equity": InstrumentSpec("_default_equity", "equity", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0),
    # CME equity index futures
    "ES": InstrumentSpec("ES", "future", multiplier=50.0, tick_size=0.25, commission_per_unit=2.25),
    "MES": InstrumentSpec("MES", "future", multiplier=5.0, tick_size=0.25, commission_per_unit=0.75),
    "NQ": InstrumentSpec("NQ", "future", multiplier=20.0, tick_size=0.25, commission_per_unit=2.25),
    "MNQ": InstrumentSpec("MNQ", "future", multiplier=2.0, tick_size=0.25, commission_per_unit=0.75),
    "YM": InstrumentSpec("YM", "future", multiplier=5.0, tick_size=1.0, commission_per_unit=2.25),
    "RTY": InstrumentSpec("RTY", "future", multiplier=50.0, tick_size=0.10, commission_per_unit=2.25),
    # Energy / metals
    "CL": InstrumentSpec("CL", "future", multiplier=1000.0, tick_size=0.01, commission_per_unit=2.50),
    "GC": InstrumentSpec("GC", "future", multiplier=100.0, tick_size=0.10, commission_per_unit=2.50),
}


def get_spec(symbol: str, overrides: dict | None = None) -> InstrumentSpec:
    """Look up an instrument spec by symbol, falling back to a plain equity default.

    `overrides` (e.g. loaded from a YAML config) is checked first so users can
    define specs for symbols not in DEFAULT_SPECS or correct the defaults.
    """
    symbol = symbol.upper()
    if overrides and symbol in overrides:
        return overrides[symbol]
    if symbol in DEFAULT_SPECS:
        return DEFAULT_SPECS[symbol]
    default = DEFAULT_SPECS["_default_equity"]
    return InstrumentSpec(
        symbol, "equity",
        multiplier=default.multiplier,
        tick_size=default.tick_size,
        commission_per_unit=default.commission_per_unit,
    )
