"""RPS 极强动量突破：横截面 RPS 排位 + 接近阶段新高。"""

from __future__ import annotations

import pandas as pd

from .base import SelectorBase


class RpsBreakoutSelector(SelectorBase):
    """120 日涨幅 RPS ≥ 阈值，且收盘接近 rolling high 突破位。"""

    def __init__(
        self,
        *,
        rps_period: int = 120,
        rps_threshold: float = 90,
        breakout_ratio: float = 0.90,
    ) -> None:
        if rps_period < 2:
            raise ValueError("rps_period 应 ≥ 2")
        self.rps_period = rps_period
        self.rps_threshold = rps_threshold
        self.breakout_ratio = breakout_ratio
        self.min_history = rps_period

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        # 横截面策略，单股过滤无意义
        return False

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        rows: list[dict[str, float | str]] = []
        min_periods = max(2, self.rps_period // 2)

        for code, df in data.items():
            if df is None or df.empty:
                continue
            hist = df[df["date"] <= date].sort_values("date")
            if len(hist) < min_periods:
                continue

            close_now = float(hist.iloc[-1]["close"])
            if len(hist) <= self.rps_period:
                continue
            close_shift = float(hist.iloc[-1 - self.rps_period]["close"])
            if close_shift <= 0:
                continue

            pct_change = (close_now - close_shift) / close_shift
            roll_high = float(
                hist["high"].rolling(self.rps_period, min_periods=min_periods).max().iloc[-1]
            )
            if pd.isna(roll_high):
                continue

            rows.append(
                {
                    "code": code,
                    "pct_change": pct_change,
                    "close": close_now,
                    "roll_high": roll_high,
                }
            )

        if not rows:
            return []

        panel = pd.DataFrame(rows)
        panel["rps"] = panel["pct_change"].rank(pct=True) * 100
        strong = panel[panel["rps"] >= self.rps_threshold]
        breakout = strong[strong["close"] >= strong["roll_high"] * self.breakout_ratio]
        return breakout["code"].astype(str).tolist()
