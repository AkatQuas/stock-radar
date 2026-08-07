"""定增公告监控：近期定向增发公告。"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from stock_radar.core.logger import get_logger

from .base import SelectorBase

logger = get_logger("strategy.private_placement")


class PrivatePlacementSelector(SelectorBase):
    """拉取东方财富定增公告，筛选近 N 日定向增发标的。"""

    min_history = 1

    def __init__(self, *, lookback_days: int = 7) -> None:
        self.lookback_days = lookback_days

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        return False

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        try:
            import akshare as ak
        except ImportError:
            logger.warning("PrivatePlacementSelector 需要 akshare，请 pip install akshare")
            return []

        try:
            df = ak.stock_qbzf_em()
        except Exception as exc:
            logger.error("获取定增数据失败: %s", exc)
            return []

        if df is None or df.empty:
            return []

        df = df[df["发行方式"] == "定向增发"]
        if df.empty:
            return []

        cutoff = (date - timedelta(days=self.lookback_days)).date()
        df["发行日期"] = pd.to_datetime(df["发行日期"], errors="coerce")
        df = df.dropna(subset=["发行日期"])
        df = df[df["发行日期"].dt.date >= cutoff]
        if df.empty:
            return []

        symbols = df["股票代码"].astype(str).str.extract(r"(\d{6})")[0].dropna()
        seen: set[str] = set()
        result: list[str] = []
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                result.append(sym)
        return result
