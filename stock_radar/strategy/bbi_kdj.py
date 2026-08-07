from __future__ import annotations

import pandas as pd

from stock_radar.core.compute import (
    bbi_deriv_uptrend,
    compute_bbi,
    compute_dif,
    compute_kdj,
    last_valid_ma_cross_up,
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from stock_radar.core.parallel_utils import parallel_select_helper


class BBIKDJSelector:
    """
    自适应 *BBI(导数)* + *KDJ* 选股器
        • BBI: 允许 bbi_q_threshold 比例的回撤
        • KDJ: J < threshold ；或位于历史 J 的 j_q_threshold 分位及以下
        • MACD: DIF > 0
        • 收盘价波动幅度 ≤ price_range_pct
    """

    def __init__(
        self,
        j_threshold: float = -5,
        bbi_min_window: int = 90,
        max_window: int = 90,
        price_range_pct: float = 100.0,
        bbi_q_threshold: float = 0.05,
        j_q_threshold: float = 0.10,
    ) -> None:
        self.j_threshold = j_threshold
        self.bbi_min_window = bbi_min_window
        self.max_window = max_window
        self.price_range_pct = price_range_pct
        self.bbi_q_threshold = bbi_q_threshold  # ← 原 q_threshold
        self.j_q_threshold = j_q_threshold  # ← 新增

    # ---------- 单支股票过滤 ---------- #
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if not passes_day_constraints_today(hist):
            return False

        hist = hist.copy()
        hist["BBI"] = compute_bbi(hist)

        # 0. 收盘价波动幅度约束（最近 max_window 根 K 线）
        win = hist.tail(self.max_window)
        high, low = win["close"].max(), win["close"].min()
        if low <= 0 or (high / low - 1) > self.price_range_pct:
            return False

        # 1. BBI 上升（允许部分回撤）
        if not bbi_deriv_uptrend(
            hist["BBI"],
            min_window=self.bbi_min_window,
            max_window=self.max_window,
            q_threshold=self.bbi_q_threshold,
        ):
            return False

        # 2. KDJ 过滤 —— 双重条件
        kdj = compute_kdj(hist)
        j_today = float(kdj.iloc[-1]["J"])

        # 最近 max_window 根 K 线的 J 分位
        j_window = kdj["J"].tail(self.max_window).dropna()
        if j_window.empty:
            return False
        j_quantile = float(j_window.quantile(self.j_q_threshold))

        if not (j_today < self.j_threshold or j_today <= j_quantile):
            return False

        # —— 2.5 60日均线条件（使用通用函数）
        hist["MA60"] = hist["close"].rolling(window=60, min_periods=1).mean()

        # 当前必须在 MA60 上方（保持原条件）
        if hist["close"].iloc[-1] < hist["MA60"].iloc[-1]:
            return False

        # 寻找最近一次“有效上穿 MA60”的 T（使用 max_window 作为回看长度，避免过旧）
        t_pos = last_valid_ma_cross_up(hist["close"], hist["MA60"], lookback_n=self.max_window)
        if t_pos is None:
            return False

        # 3. MACD：DIF > 0
        hist["DIF"] = compute_dif(hist)
        if hist["DIF"].iloc[-1] <= 0:
            return False

        # 4. 当日：收盘>长期线 且 短期线>长期线
        return zx_condition_at_positions(
            hist, require_close_gt_long=True, require_short_gt_long=True, pos=None
        )

    # ---------- 多股票批量 ---------- #
    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        for code, df in data.items():
            hist = df[df["date"] <= date]
            if hist.empty:
                continue
            # 额外预留 20 根 K 线缓冲
            hist = hist.tail(self.max_window + 20)
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
