"""高旗形整理：强动量后极度收敛缩量。"""

from __future__ import annotations

import pandas as pd

from .base import SelectorBase


class HighTightFlagSelector(SelectorBase):
    """40 日强动量 + 10 日收敛 + 高位抗跌 + 缩量。"""

    min_history = 40

    def __init__(
        self,
        *,
        momentum_window: int = 40,
        consolidation_window: int = 10,
        momentum_ratio: float = 1.6,
        consolidation_ratio: float = 1.15,
        high_level_ratio: float = 0.8,
        vol_shrink_ratio: float = 0.6,
        vol_ma_window: int = 20,
    ) -> None:
        self.momentum_window = momentum_window
        self.consolidation_window = consolidation_window
        self.momentum_ratio = momentum_ratio
        self.consolidation_ratio = consolidation_ratio
        self.high_level_ratio = high_level_ratio
        self.vol_shrink_ratio = vol_shrink_ratio
        self.vol_ma_window = vol_ma_window
        self.min_history = momentum_window

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if len(hist) < self.min_history:
            return False

        tail_m = hist.tail(self.momentum_window)
        tail_c = hist.tail(self.consolidation_window)

        high_m = float(tail_m["high"].max())
        low_m = float(tail_m["low"].min())
        high_c = float(tail_c["high"].max())
        low_c = float(tail_c["low"].min())
        if low_m <= 0 or low_c <= 0:
            return False

        momentum = high_m / low_m > self.momentum_ratio
        consolidation = high_c / low_c < self.consolidation_ratio
        high_level = low_c >= high_m * self.high_level_ratio

        vol_slice = hist["volume"].iloc[-(self.vol_ma_window + 1) : -1]
        if vol_slice.empty:
            return False
        vol_ma = float(vol_slice.mean())
        shrink = float(hist["volume"].iloc[-1]) < vol_ma * self.vol_shrink_ratio
        return bool(momentum and consolidation and high_level and shrink)
