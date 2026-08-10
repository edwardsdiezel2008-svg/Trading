"""Instrument specifications: contract multipliers, tick sizes, and asset class.

Equities (NASDAQ etc.) default to multiplier=1 (1 share = 1 point of P&L per $1 move).
Futures need a real point multiplier or P&L will be wrong by orders of magnitude.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    asset_class: str  # "equity", "future", or "crypto"
    multiplier: float  # $ P&L per 1.0 price move, per contract/share/coin
    tick_size: float  # minimum price increment
    commission_per_unit: float  # $ per share/contract/coin, one side
    fractional_units: bool = False  # True for assets tradable in fractional amounts (crypto)
    # Percentage-of-notional costs, one side each (added on top of
    # commission_per_unit). A fixed $-per-unit fee makes no sense for an
    # asset whose price moves from $17k to $150k+ within one backtest -
    # exchange fees and market-order slippage both scale with trade value,
    # not with unit count. Default 0.0 so existing equity/futures specs
    # (which use commission_per_unit instead) are unaffected.
    commission_pct: float = 0.0
    slippage_pct: float = 0.0


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
    # QQQ (Invesco QQQ Trust) - the Nasdaq-100 dashboard track's underlying:
    # real NQ/MNQ futures tick data isn't available from any free, no-API-key
    # source, so this liquid ETF proxy is traded instead with plain equity
    # economics ($0 commission matches most modern brokers' ETF trades; 0.05%
    # slippage is a conservative estimate for a highly liquid product).
    "QQQ": InstrumentSpec("QQQ", "equity", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, commission_pct=0.0, slippage_pct=0.0005),
    # Energy / metals
    "CL": InstrumentSpec("CL", "future", multiplier=1000.0, tick_size=0.01, commission_per_unit=2.50),
    "GC": InstrumentSpec("GC", "future", multiplier=100.0, tick_size=0.10, commission_per_unit=2.50),
    # Crypto - fractional units matter here: BTC at $60k+ means a $100 account
    # can't buy a whole "1 unit" the way a stock/futures position sizer assumes.
    #
    # commission_pct/slippage_pct: 0.075% taker fee (Crypto.com Exchange's
    # standard non-VIP taker rate) + 0.05% assumed market-order slippage,
    # one side each - a good-faith realistic estimate, not a live-verified
    # fee schedule (this sandbox can't reach the exchange's docs to check).
    # ~0.25% round trip. Previously this was 0.0 - i.e. every backtested
    # return on this project was frictionless and therefore not a real
    # signal of whether any strategy could actually be profitable.
    "_default_crypto": InstrumentSpec("_default_crypto", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "BTC_USDT": InstrumentSpec("BTC_USDT", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "BTC_USD": InstrumentSpec("BTC_USD", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "BTC-USD": InstrumentSpec("BTC-USD", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "ETH_USDT": InstrumentSpec("ETH_USDT", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "ETH_USD": InstrumentSpec("ETH_USD", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "ETH-USD": InstrumentSpec("ETH-USD", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "SOL_USDT": InstrumentSpec("SOL_USDT", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "SOL_USD": InstrumentSpec("SOL_USD", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
    "SOL-USD": InstrumentSpec("SOL-USD", "crypto", multiplier=1.0, tick_size=0.01, commission_per_unit=0.0, fractional_units=True, commission_pct=0.00075, slippage_pct=0.0005),
}

_CRYPTO_QUOTE_CURRENCIES = ("USDT", "USDC", "USD", "BTC", "ETH")


def _looks_like_crypto_pair(symbol: str) -> bool:
    """Heuristic for symbols not explicitly listed: BTC_USDT, ETH-USD, SOL/USDC,
    etc. - a separator plus a recognizable quote currency. Plain equity tickers
    (AAPL, MSFT) have neither, so this doesn't misfire on those.
    """
    for sep in ("_", "-", "/"):
        if sep in symbol:
            quote = symbol.split(sep)[-1]
            if quote in _CRYPTO_QUOTE_CURRENCIES:
                return True
    return False


def get_spec(symbol: str, overrides: dict | None = None) -> InstrumentSpec:
    """Look up an instrument spec by symbol, falling back to a plain equity
    default - or a fractional-unit crypto default if the symbol looks like a
    crypto pair (e.g. 'SOL_USDT') and isn't explicitly listed above.

    `overrides` (e.g. loaded from a YAML config) is checked first so users can
    define specs for symbols not in DEFAULT_SPECS or correct the defaults.
    """
    symbol = symbol.upper()
    if overrides and symbol in overrides:
        return overrides[symbol]
    if symbol in DEFAULT_SPECS:
        return DEFAULT_SPECS[symbol]

    if _looks_like_crypto_pair(symbol):
        default = DEFAULT_SPECS["_default_crypto"]
        return InstrumentSpec(
            symbol, "crypto",
            multiplier=default.multiplier,
            tick_size=default.tick_size,
            commission_per_unit=default.commission_per_unit,
            fractional_units=True,
            commission_pct=default.commission_pct,
            slippage_pct=default.slippage_pct,
        )

    default = DEFAULT_SPECS["_default_equity"]
    return InstrumentSpec(
        symbol, "equity",
        multiplier=default.multiplier,
        tick_size=default.tick_size,
        commission_per_unit=default.commission_per_unit,
        commission_pct=default.commission_pct,
        slippage_pct=default.slippage_pct,
    )
