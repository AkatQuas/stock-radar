from __future__ import annotations

import pandas as pd

from stock_radar.core.compute import (
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from stock_radar.core.parallel_utils import parallel_select_helper


class OscillationGrowthSelector:
    """
    震荡后几根 K 线上攻选股器

    1. **震荡区间** — 在 growth_bars 之前的 oscillation_days 根 K 线内，
       收盘价波动幅度 ``(max/min - 1)`` ≤ ``oscillation_pct``。
    2. **增长模式** — 最近 growth_bars 根 K 线收盘价严格递增，
       累计涨幅 ≥ ``growth_pct``；可选要求每根收阳。
    3. **突破** — 最后一根收盘价 ≥ 震荡区间最高收盘价（可选）。
    4. **知行线** — 收盘>长期线 且 短期线>长期线（可选）。
    """

    def __init__(
        self,
        *,
        oscillation_days: int = 15,
        oscillation_pct: float = 0.08,
        growth_bars: int = 3,
        growth_pct: float = 0.03,
        require_bullish: bool = True,
        require_monotonic_close: bool = True,
        require_breakout: bool = True,
        use_zx_filter: bool = True,
    ) -> None:
        if oscillation_days < 3:
            raise ValueError("oscillation_days 应 ≥ 3")
        if not (0 < oscillation_pct < 1):
            raise ValueError("oscillation_pct 应位于 (0, 1) 区间")
        if growth_bars < 2:
            raise ValueError("growth_bars 应 ≥ 2")
        if not (0 < growth_pct < 1):
            raise ValueError("growth_pct 应位于 (0, 1) 区间")

        self.oscillation_days = oscillation_days
        self.oscillation_pct = oscillation_pct
        self.growth_bars = growth_bars
        self.growth_pct = growth_pct
        self.require_bullish = require_bullish
        self.require_monotonic_close = require_monotonic_close
        self.require_breakout = require_breakout
        self.use_zx_filter = use_zx_filter
        self.min_history = oscillation_days + growth_bars + 5

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or hist.empty:
            return False

        hist = hist.copy().sort_values("date")
        if len(hist) < self.min_history:
            return False

        if not passes_day_constraints_today(hist):
            return False

        total_need = self.oscillation_days + self.growth_bars
        if len(hist) < total_need:
            return False

        growth = hist.tail(self.growth_bars)
        oscillation = hist.iloc[-total_need : -self.growth_bars]

        osc_close = oscillation["close"].astype(float)
        osc_low = float(osc_close.min())
        osc_high = float(osc_close.max())
        if osc_low <= 0:
            return False
        if (osc_high / osc_low - 1.0) > self.oscillation_pct:
            return False

        growth_close = growth["close"].astype(float).values
        if growth_close[0] <= 0:
            return False

        if self.require_monotonic_close and not all(
            growth_close[i] > growth_close[i - 1] for i in range(1, len(growth_close))
        ):
            return False

        if (growth_close[-1] / growth_close[0] - 1.0) < self.growth_pct:
            return False

        if self.require_bullish:
            opens = growth["open"].astype(float).values
            if not all(growth_close[i] >= opens[i] for i in range(len(growth_close))):
                return False

        if self.require_breakout and growth_close[-1] < osc_high:
            return False

        if not self.use_zx_filter:
            return True

        return zx_condition_at_positions(
            hist, require_close_gt_long=True, require_short_gt_long=True, pos=None
        )

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        for code, df in data.items():
            if df is None or df.empty:
                continue
            hist = df[df["date"] <= date].tail(self.min_history + 10)
            if len(hist) < self.min_history:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
