"""海龟交易：20 日新高突破 + 成交额过亿 + 阳线过滤。"""

from __future__ import annotations

import pandas as pd

from .base import SelectorBase


class TurtleTradeSelector(SelectorBase):
    """A 股改良海龟突破：新高 + 流动性 + 防诱多阳线。"""

    min_history = 21

    def __init__(
        self,
        *,
        breakout_window: int = 20,
        min_amount: float = 100_000_000,
        require_bullish: bool = True,
        require_higher_close: bool = True,
    ) -> None:
        self.breakout_window = breakout_window
        self.min_amount = min_amount
        self.require_bullish = require_bullish
        self.require_higher_close = require_higher_close
        self.min_history = breakout_window + 1

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if len(hist) < self.min_history:
            return False

        df = hist.copy()
        df["high_n"] = df["high"].shift(1).rolling(self.breakout_window).max()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        if pd.isna(last["high_n"]):
            return False

        breakout = float(last["close"]) > float(last["high_n"])
        amount = float(last.get("amount", 0) or 0)
        liquid = amount > self.min_amount

        is_yang = (not self.require_bullish) or float(last["close"]) > float(last["open"])
        is_up = (not self.require_higher_close) or float(last["close"]) > float(prev["close"])
        return bool(breakout and liquid and is_yang and is_up)
