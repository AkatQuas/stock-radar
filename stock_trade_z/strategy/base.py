"""选股策略基类：与 Sequoia-X strategy/base 对齐的本地适配层。"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from stock_trade_z.core.parallel_utils import parallel_select_helper


class SelectorBase(ABC):
    """单股过滤 + 批量并行选股的通用基类。

    子类实现 ``_passes_filters``；跨截面策略可覆盖 ``select``。
    """

    min_history: int = 20

    @abstractmethod
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        """判断单只股票历史 K 线是否满足策略。"""

    def _history_buffer(self) -> int:
        """在 ``min_history`` 之外额外保留的 K 线根数。"""
        return 5

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        need_len = self.min_history + self._history_buffer()
        tasks: list[tuple[str, pd.DataFrame]] = []
        for code, df in data.items():
            if df is None or df.empty:
                continue
            hist = df[df["date"] <= date].tail(need_len)
            if len(hist) < self.min_history:
                continue
            tasks.append((code, hist))
        return parallel_select_helper(self, tasks)
