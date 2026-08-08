"""Run every strategy against every instrument's bars and produce a comparison
report: a metrics table (CSV), equity curve plots (PNG), and a plain-English
regime-attribution summary (TXT) explaining why each strategy performed the
way it did.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .engine import run_backtest
from .instruments import get_spec
from .metrics import metrics_table
from .regime import classify_regimes, explain_result
from .strategies import build_default_strategies


def run_comparison(
    bars_by_symbol: dict[str, pd.DataFrame],
    strategies=None,
    initial_capital: float = 100_000.0,
    freq_hint: str | None = None,
    instrument_overrides: dict | None = None,
    output_dir: str = "reports",
) -> dict:
    """bars_by_symbol: {"AAPL": bars_df, "ES": bars_df, ...}

    Returns {"metrics": DataFrame, "explanations": str, "results": [BacktestResult, ...]}
    and writes metrics.csv, equity_curves.png, explanations.txt into output_dir.
    """
    strategies = strategies or build_default_strategies()
    os.makedirs(output_dir, exist_ok=True)

    results_with_capital = []
    all_results = []
    explanation_lines = []

    fig, ax = plt.subplots(figsize=(11, 6))

    for symbol, bars in bars_by_symbol.items():
        spec = get_spec(symbol, instrument_overrides)
        regimes = classify_regimes(bars)

        for strategy in strategies:
            result = run_backtest(bars, strategy, spec, initial_capital=initial_capital)
            results_with_capital.append((result, initial_capital))
            all_results.append(result)
            explanation_lines.append(explain_result(result, regimes))

            normalized = result.equity_curve / initial_capital
            ax.plot(normalized.index, normalized.values, label=f"{strategy.name} [{symbol}]", linewidth=1)

    table = metrics_table(results_with_capital, freq_hint=freq_hint)

    ax.axhline(1.0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_title("Equity Curves (normalized to 1.0 = starting capital)")
    ax.set_ylabel("Equity / Initial Capital")
    ax.legend(fontsize=7, loc="best", ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "equity_curves.png"), dpi=150)
    plt.close(fig)

    table.to_csv(os.path.join(output_dir, "metrics.csv"), index=False)

    explanations_text = "\n\n".join(explanation_lines)
    with open(os.path.join(output_dir, "explanations.txt"), "w") as f:
        f.write(explanations_text)

    return {"metrics": table, "explanations": explanations_text, "results": all_results}
