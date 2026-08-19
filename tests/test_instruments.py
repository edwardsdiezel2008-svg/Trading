import sys

sys.path.insert(0, ".")

from src.backtest.instruments import DEFAULT_SPECS, InstrumentSpec, _looks_like_crypto_pair, get_spec


def test_looks_like_crypto_pair_true_for_underscore_dash_and_slash_separated_pairs():
    assert _looks_like_crypto_pair("BTC_USDT")
    assert _looks_like_crypto_pair("ETH-USD")
    assert _looks_like_crypto_pair("SOL/USDC")


def test_looks_like_crypto_pair_false_for_symbols_without_a_recognized_quote_currency():
    assert not _looks_like_crypto_pair("AAPL")  # no separator at all
    assert not _looks_like_crypto_pair("MNQ")  # futures ticker, no separator
    assert not _looks_like_crypto_pair("BRK-B")  # equity with a dash, but "B" isn't a quote currency


def test_get_spec_known_symbol_returns_the_exact_default_spec():
    assert get_spec("MNQ") is DEFAULT_SPECS["MNQ"]
    assert get_spec("MNQ").multiplier == 2.0


def test_get_spec_is_case_insensitive():
    assert get_spec("mnq") == get_spec("MNQ")


def test_get_spec_unlisted_equity_like_symbol_falls_back_to_equity_default():
    spec = get_spec("ZZZZ")
    assert spec.symbol == "ZZZZ"
    assert spec.asset_class == "equity"
    assert spec.multiplier == DEFAULT_SPECS["_default_equity"].multiplier
    assert spec.fractional_units is False


def test_get_spec_unlisted_crypto_pair_falls_back_to_crypto_default():
    spec = get_spec("DOGE_USDT")
    assert spec.symbol == "DOGE_USDT"
    assert spec.asset_class == "crypto"
    assert spec.fractional_units is True
    assert spec.commission_pct == DEFAULT_SPECS["_default_crypto"].commission_pct
    assert spec.slippage_pct == DEFAULT_SPECS["_default_crypto"].slippage_pct


def test_get_spec_overrides_take_precedence_over_default_specs():
    custom = InstrumentSpec("MNQ", "future", multiplier=999.0, tick_size=0.25, commission_per_unit=0.0)
    assert get_spec("MNQ", overrides={"MNQ": custom}) is custom


def test_get_spec_overrides_do_not_affect_symbols_not_in_the_override_dict():
    custom = InstrumentSpec("MNQ", "future", multiplier=999.0, tick_size=0.25, commission_per_unit=0.0)
    assert get_spec("MES", overrides={"MNQ": custom}) is DEFAULT_SPECS["MES"]


# Real CME/COMEX/NYMEX contract multipliers - a typo here silently makes
# every dollar P&L figure for that track wrong by whatever factor the typo
# introduces (e.g. a missing digit is a 10x error), so pin them directly
# rather than relying on the numbers only ever being read, never checked.
def test_futures_multipliers_match_real_exchange_contract_specs():
    expected = {
        "ES": 50.0, "MES": 5.0,
        "NQ": 20.0, "MNQ": 2.0,
        "YM": 5.0, "MYM": 0.5,
        "RTY": 50.0, "M2K": 5.0,
        "CL": 1000.0, "MCL": 100.0,
        "GC": 100.0, "MGC": 10.0,
    }
    for symbol, multiplier in expected.items():
        assert DEFAULT_SPECS[symbol].multiplier == multiplier, f"{symbol}: expected {multiplier}"
