"""均线+成交量选股：5 日均线上穿 20 日均线且放量。"""

from __future__ import annotations

import pandas as pd

from .base import SelectorBase


class MaVolumeSelector(SelectorBase):
    """5/20 日均线金叉 + 当日成交量 > 20 日均量 × vol_multiple。"""

    min_history = 21

    def __init__(
        self,
        *,
        short_ma: int = 5,
        long_ma: int = 20,
        vol_multiple: float = 1.5,
    ) -> None:
        if short_ma >= long_ma:
            raise ValueError("short_ma 应 < long_ma")
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.vol_multiple = vol_multiple
        self.min_history = long_ma + 1

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if len(hist) < self.min_history:
            return False

        df = hist.copy()
        df["ma_short"] = df["close"].rolling(self.short_ma).mean()
        df["ma_long"] = df["close"].rolling(self.long_ma).mean()
        df["vol_ma"] = df["volume"].rolling(self.long_ma).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        if pd.isna(last["ma_short"]) or pd.isna(last["ma_long"]) or pd.isna(last["vol_ma"]):
            return False

        golden_cross = prev["ma_short"] < prev["ma_long"] and last["ma_short"] > last["ma_long"]
        volume_surge = float(last["volume"]) > float(last["vol_ma"]) * self.vol_multiple
        return bool(golden_cross and volume_surge)
