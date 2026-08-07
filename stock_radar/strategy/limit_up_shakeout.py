"""涨停洗盘：昨日涨停后今日放量收阴但不破昨收。"""

from __future__ import annotations

import pandas as pd

from .base import SelectorBase


class LimitUpShakeoutSelector(SelectorBase):
    """涨停次日放量阴线洗盘，低点不破昨日收盘。"""

    min_history = 3

    def __init__(
        self,
        *,
        limit_up_ratio: float = 1.095,
        vol_multiple: float = 2.0,
    ) -> None:
        self.limit_up_ratio = limit_up_ratio
        self.vol_multiple = vol_multiple

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if len(hist) < self.min_history:
            return False

        prev2 = hist.iloc[-3]
        prev1 = hist.iloc[-2]
        today = hist.iloc[-1]

        limit_up_yesterday = float(prev1["close"]) >= float(prev2["close"]) * self.limit_up_ratio
        bearish_today = float(today["close"]) < float(today["open"])
        volume_surge = float(today["volume"]) > float(prev1["volume"]) * self.vol_multiple
        support_hold = float(today["low"]) >= float(prev1["close"])
        return bool(limit_up_yesterday and bearish_today and volume_surge and support_hold)
