"""上升趋势跌停：趋势中放量跌停，捕捉错杀。"""

from __future__ import annotations

import pandas as pd

from .base import SelectorBase


class UptrendLimitDownSelector(SelectorBase):
    """MA20 > MA60 上升趋势中，当日放量跌停。"""

    min_history = 60

    def __init__(
        self,
        *,
        short_ma: int = 20,
        long_ma: int = 60,
        limit_down_ratio: float = 0.905,
        vol_multiple: float = 2.0,
    ) -> None:
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.limit_down_ratio = limit_down_ratio
        self.vol_multiple = vol_multiple
        self.min_history = long_ma

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if len(hist) < self.min_history:
            return False

        df = hist.copy()
        df["ma_short"] = df["close"].rolling(self.short_ma).mean()
        df["ma_long"] = df["close"].rolling(self.long_ma).mean()
        df["vol_ma"] = df["volume"].rolling(self.short_ma).mean()

        prev = df.iloc[-2]
        today = df.iloc[-1]
        if pd.isna(prev["ma_short"]) or pd.isna(prev["ma_long"]) or pd.isna(today["vol_ma"]):
            return False

        uptrend = float(prev["ma_short"]) > float(prev["ma_long"])
        limit_down = float(today["close"]) <= float(prev["close"]) * self.limit_down_ratio
        volume_surge = float(today["volume"]) > float(today["vol_ma"]) * self.vol_multiple
        return bool(uptrend and limit_down and volume_surge)
