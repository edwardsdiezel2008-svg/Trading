from .base import Strategy
from .mean_reversion import BollingerReversion, RSIReversion, ZScoreReversion
from .trend import DonchianBreakout, MACDMomentum, MovingAverageCrossover
from .volatility import ATRVolatilityBreakout

ALL_STRATEGY_CLASSES = [
    MovingAverageCrossover,
    DonchianBreakout,
    MACDMomentum,
    RSIReversion,
    BollingerReversion,
    ZScoreReversion,
    ATRVolatilityBreakout,
]


def build_default_strategies() -> list[Strategy]:
    """One instance of every strategy with default parameters."""
    return [cls() for cls in ALL_STRATEGY_CLASSES]


__all__ = [
    "Strategy",
    "MovingAverageCrossover",
    "DonchianBreakout",
    "MACDMomentum",
    "RSIReversion",
    "BollingerReversion",
    "ZScoreReversion",
    "ATRVolatilityBreakout",
    "ALL_STRATEGY_CLASSES",
    "build_default_strategies",
]
