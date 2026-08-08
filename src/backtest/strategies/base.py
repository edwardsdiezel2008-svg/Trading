"""Common interface all strategies implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Strategy(ABC):
    """Base class for a backtestable strategy.

    Subclasses implement `generate_signals`, returning a Series of *target
    positions* aligned to the bars' index: 1 = fully long, -1 = fully short,
    0 = flat. The engine is responsible for turning that into fills, so
    strategies never touch prices directly except to compute indicators -
    this keeps them free of lookahead bias by construction (the engine always
    executes a signal on the *next* bar's open).
    """

    params: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def generate_signals(self, bars: pd.DataFrame) -> pd.Series:
        """bars has columns open/high/low/close/volume, DatetimeIndex.
        Returns a Series of target positions in {-1, 0, 1} indexed like bars.
        """
        raise NotImplementedError
