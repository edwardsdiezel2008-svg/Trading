"""Parameter sensitivity sweeps: is a strategy's edge a plateau or a spike?

A backtest run with one textbook parameter set (e.g. MA_Crossover(10/50))
tells you nothing about whether 10/50 was a reasonable choice or a fluke that
happened to fit this exact dataset. This sweeps each of a strategy's
PARAM_SPACE entries one at a time - holding everything else fixed - and
reports how the result moves. A robust edge stays profitable across nearby
parameter values (a plateau); an overfit one looks great at exactly one
setting and falls apart next to it (a spike).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import run_backtest
from .instruments import InstrumentSpec
from .metrics import compute_metrics


@dataclass
class SensitivityResult:
    strategy_name: str
    instrument: str
    detail: pd.DataFrame
    summary: pd.DataFrame


def param_sensitivity(
    bars: pd.DataFrame,
    strategy_cls,
    spec: InstrumentSpec,
    base_params: dict | None = None,
    metric: str = "sharpe",
    initial_capital: float = 100_000.0,
    freq_hint: str | None = None,
    **engine_kwargs,
) -> SensitivityResult:
    param_space = getattr(strategy_cls, "PARAM_SPACE", None)
    if not param_space:
        raise ValueError(f"{strategy_cls.__name__} has no PARAM_SPACE defined for sensitivity analysis.")
    base_params = base_params or {}

    rows = []
    for pname, values in param_space.items():
        for v in values:
            combo = dict(base_params)
            combo[pname] = v
            strat = strategy_cls(params=combo)
            try:
                res = run_backtest(bars, strat, spec, initial_capital=initial_capital, **engine_kwargs)
                m = compute_metrics(res, initial_capital, freq_hint=freq_hint)
            except Exception:
                m = {"total_return": np.nan, "sharpe": np.nan, "max_drawdown": np.nan, "num_trades": 0}
            rows.append({
                "parameter": pname, "value": v,
                "total_return": m.get("total_return"), "sharpe": m.get("sharpe"),
                "max_drawdown": m.get("max_drawdown"), "num_trades": m.get("num_trades"),
            })

    detail = pd.DataFrame(rows)
    summary = detail.groupby("parameter").agg(
        n_values=("value", "count"),
        metric_mean=(metric, "mean"),
        metric_std=(metric, "std"),
        metric_min=(metric, "min"),
        metric_max=(metric, "max"),
        frac_profitable=("total_return", lambda s: float((s > 0).mean())),
    )
    return SensitivityResult(strategy_name=strategy_cls.__name__, instrument=spec.symbol, detail=detail, summary=summary)
