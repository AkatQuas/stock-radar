from __future__ import annotations

import pandas as pd

from stock_radar.core.compute import (
    compute_kdj,
    last_valid_ma_cross_up,
    passes_day_constraints_today,
)
from stock_radar.core.parallel_utils import parallel_select_helper


class MACrossSelector:
    """
    Simple MA crossover strategy with volume confirmation

    Conditions:
    1. Short MA crosses above Long MA recently
    2. Price above both MAs
    3. Volume above average
    4. J value low (oversold)
    """

    def __init__(
        self,
        *,
        short_ma: int = 5,
        long_ma: int = 20,
        vol_multiple: float = 1.5,
        j_threshold: float = 15,
        lookback_n: int = 10,
    ) -> None:
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.vol_multiple = vol_multiple
        self.j_threshold = j_threshold
        self.lookback_n = lookback_n

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist.empty or len(hist) < max(self.long_ma, self.lookback_n) + 5:
            return False

        hist = hist.copy()

        # Day constraints
        if not passes_day_constraints_today(hist):
            return False

        # Calculate MAs
        hist["MA_short"] = hist["close"].rolling(window=self.short_ma).mean()
        hist["MA_long"] = hist["close"].rolling(window=self.long_ma).mean()

        # 1. Find recent crossover
        cross_pos = last_valid_ma_cross_up(
            hist["MA_short"], hist["MA_long"], lookback_n=self.lookback_n
        )
        if cross_pos is None:
            return False

        # 2. Price above both MAs
        close_today = hist["close"].iloc[-1]
        if close_today < hist["MA_short"].iloc[-1]:
            return False
        if close_today < hist["MA_long"].iloc[-1]:
            return False

        # 3. Volume confirmation
        vol_today = hist["volume"].iloc[-1]
        vol_avg = hist["volume"].tail(20).mean()
        if vol_today < vol_avg * self.vol_multiple:
            return False

        # 4. KDJ oversold
        kdj = compute_kdj(hist)
        return not kdj["J"].iloc[-1] > self.j_threshold

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        need_len = max(self.long_ma, self.lookback_n) + 20
        for code, df in data.items():
            hist = df[df["date"] <= date].tail(need_len)
            if len(hist) < need_len:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
