from .base import Strategy
from .mean_reversion import (
    BollingerReversion,
    CCIReversion,
    RSIReversion,
    StochasticReversion,
    VWAPReversion,
    ZScoreReversion,
)
from .patterns import EngulfingReversal, InsideBarBreakout, OpeningRangeBreakout, OpeningRangeBreakoutATRTarget
from .profile import TPOReversion, VolumeProfileReversion
from .regime_filter import RegimeFilteredStrategy
from .trend import DonchianBreakout, MACDMomentum, MovingAverageCrossover, ParabolicSAR
from .volatility import ATRVolatilityBreakout, KeltnerChannelBreakout, Supertrend

ALL_STRATEGY_CLASSES = [
    MovingAverageCrossover,
    DonchianBreakout,
    MACDMomentum,
    ParabolicSAR,
    RSIReversion,
    BollingerReversion,
    ZScoreReversion,
    StochasticReversion,
    CCIReversion,
    ATRVolatilityBreakout,
    Supertrend,
    KeltnerChannelBreakout,
    VWAPReversion,
    EngulfingReversal,
    InsideBarBreakout,
    OpeningRangeBreakout,
    OpeningRangeBreakoutATRTarget,
    VolumeProfileReversion,
    TPOReversion,
]


def build_default_strategies() -> list[Strategy]:
    """One instance of every strategy with default parameters."""
    return [cls() for cls in ALL_STRATEGY_CLASSES]


__all__ = [
    "Strategy",
    "MovingAverageCrossover",
    "DonchianBreakout",
    "MACDMomentum",
    "ParabolicSAR",
    "RSIReversion",
    "BollingerReversion",
    "ZScoreReversion",
    "StochasticReversion",
    "CCIReversion",
    "ATRVolatilityBreakout",
    "Supertrend",
    "KeltnerChannelBreakout",
    "VWAPReversion",
    "EngulfingReversal",
    "InsideBarBreakout",
    "OpeningRangeBreakout",
    "OpeningRangeBreakoutATRTarget",
    "VolumeProfileReversion",
    "TPOReversion",
    "RegimeFilteredStrategy",
    "ALL_STRATEGY_CLASSES",
    "build_default_strategies",
]
