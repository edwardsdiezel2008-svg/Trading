"""One-off diagnostic: dump every USD/USDT-quoted instrument symbol Crypto.com
Exchange's public get-tickers endpoint actually returns, so the memecoin
wide-scan candidate list can be built from the real listing instead of
guessing ticker names and hoping they exist.

Not part of the regular pipeline - run manually, read the output, delete
or leave in place for future re-runs when re-curating the list.

Usage: python scripts/list_all_tickers.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from scripts.fetch_market_data import fetch_tickers, _ticker_symbol


def main():
    tickers = fetch_tickers()
    symbols = sorted({_ticker_symbol(t) for t in tickers})
    usd_symbols = [s for s in symbols if s.endswith("_USD") or s.endswith("_USDT")]
    print(f"Total instruments: {len(symbols)}")
    print(f"USD/USDT-quoted: {len(usd_symbols)}")
    print()
    for s in usd_symbols:
        print(s)


if __name__ == "__main__":
    main()
