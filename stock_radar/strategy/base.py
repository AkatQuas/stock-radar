"""选股策略基类与统一 Selector 接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from stock_radar.core.parallel_utils import parallel_select_helper


@runtime_checkable
class Selector(Protocol):
    """K 线选股器接口：select(date, data) -> list[str]。"""

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        **ctx: Any,
    ) -> list[str]: ...


@runtime_checkable
class VectorSelector(Selector, Protocol):
    """向量 pipeline selector：prepare_df + vec_picks_from_prepared 批量路径。

    实现类：``PipelineSelector`` 子类（如 ``B1Selector``, ``BrickChartSelector``）。
    """

    def passes_df_on_date(self, df: pd.DataFrame, date: pd.Timestamp) -> bool: ...

    def prepare_df(self, df: pd.DataFrame) -> pd.DataFrame: ...

    def vec_picks_from_prepared(
        self,
        df: pd.DataFrame,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> list[pd.Timestamp]: ...


def is_vector_selector(selector: object) -> bool:
    """True when selector exposes the vector pipeline interface."""
    return isinstance(selector, VectorSelector)


@runtime_checkable
class PoolSelector(Protocol):
    """股池选股器接口：select(date, data, pools) -> list[str]。"""

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
        **ctx: Any,
    ) -> list[str]: ...


def run_select(
    selector: Selector | PoolSelector,
    date: pd.Timestamp,
    data: dict[str, pd.DataFrame],
    *,
    pools: dict[str, pd.DataFrame] | None = None,
) -> list[str]:
    """统一调用入口：自动分发 K 线 / 股池 selector。"""
    if pools is not None:
        return selector.select(date, data, pools)  # type: ignore[call-arg]
    return selector.select(date, data)  # type: ignore[call-arg]


class SelectorBase(ABC):
    """单股过滤 + 批量并行选股的通用基类。

    子类实现 ``_passes_filters``；跨截面策略可覆盖 ``select`` 或 ``_slice_history``。
    """

    min_history: int = 20

    @abstractmethod
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        """判断单只股票历史 K 线是否满足策略。"""

    def _history_buffer(self) -> int:
        """在 ``min_history`` 之外额外保留的 K 线根数。"""
        return 5

    def _use_full_history(self) -> bool:
        """为 True 时不截断 tail，仅按 min_history 过滤。"""
        return False

    def _slice_history(self, df: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame | None:
        hist = df[df["date"] <= date]
        if hist.empty:
            return None
        if self._use_full_history():
            if len(hist) < self.min_history:
                return None
            return hist
        need_len = self.min_history + self._history_buffer()
        hist = hist.tail(need_len)
        if len(hist) < self.min_history:
            return None
        return hist

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame], **ctx: Any) -> list[str]:
        tasks: list[tuple[str, pd.DataFrame]] = []
        for code, df in data.items():
            if df is None or df.empty:
                continue
            hist = self._slice_history(df, date)
            if hist is not None:
                tasks.append((code, hist))
        return parallel_select_helper(self, tasks)


class RiskSelectorBase(SelectorBase):
    """风控 selector 默认使用截至当日的完整历史 K 线。"""

    def _use_full_history(self) -> bool:
        return True


class PoolSelectorBase(ABC):
    """股池战法基类：子类实现 ``_select_from_pool``。"""

    def __init__(self, pool: str = "ztgc") -> None:
        self.pool = pool

    @abstractmethod
    def _select_from_pool(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pool_df: pd.DataFrame,
    ) -> list[str]:
        """从单个股池 DataFrame 中筛选标的。"""

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
        **ctx: Any,
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        return self._select_from_pool(date, data, pool_df)
