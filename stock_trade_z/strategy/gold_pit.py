from __future__ import annotations

import numpy as np
import pandas as pd

from stock_trade_z.core.compute import (
    compute_cci14_cci84,
    compute_pit_and_trap,
    passes_day_constraints_today,
)
from stock_trade_z.core.parallel_utils import parallel_select_helper


class GoldPitSelector:
    def __init__(
        self,
        gold_pit_threshold: float = -10.0,
        cci_overbought_threshold: float = 100.0,
        cci_extreme_overbought_threshold: float = 200.0,
        cci_oversold_threshold: float = -100.0,
    ) -> None:
        self.gold_pit_threshold = gold_pit_threshold
        self.cci_overbought_threshold = cci_overbought_threshold
        self.cci_extreme_overbought_threshold = cci_extreme_overbought_threshold
        self.cci_oversold_threshold = cci_oversold_threshold

    # ---------- 单支股票过滤 ---------- #
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if not passes_day_constraints_today(hist):
            return False
        hist = compute_pit_and_trap(hist, self.gold_pit_threshold)
        hist = compute_cci14_cci84(hist)
        # CCI Sell Signals (overbought)
        hist["cci14_overbought_sell"] = np.where(
            hist["CCI14"] > self.cci_overbought_threshold, 1, 0
        )
        hist["cci14_extreme_overbought_sell"] = np.where(
            hist["CCI14"] > self.cci_extreme_overbought_threshold, 1, 0
        )
        hist["cci84_overbought_sell"] = np.where(
            hist["CCI84"] > self.cci_overbought_threshold, 1, 0
        )

        # CCI Buy Signal (oversold, optional reference)
        hist["cci14_oversold_buy"] = np.where(hist["CCI14"] < self.cci_oversold_threshold, 1, 0)
        return bool(hist["cci14_oversold_buy"].iloc[-1] == 1 and hist["gold_pit"].iloc[-1] == -120)

    # ---------- 多股票批量 ---------- #
    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        for code, df in data.items():
            hist = df[df["date"] <= date]
            if hist.empty:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
