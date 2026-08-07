from __future__ import annotations

import numpy as np
import pandas as pd

from stock_radar.core.compute import (
    compute_kdj,
    last_valid_ma_cross_up,
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from stock_radar.core.parallel_utils import parallel_select_helper


class MA60CrossVolumeWaveSelector:
    """
    条件：
    1) 当日 J 绝对低或相对低（J < j_threshold 或 J ≤ 近 max_window 根 J 的 j_q_threshold 分位）
    2) 最近 lookback_n 内，存在一次“有效上穿 MA60”（t-1 收盘 < MA60, t 收盘 ≥ MA60）；
       且从该上穿日 T 到今天的“上涨波段”日均成交量 ≥ 上穿前等长窗口的日均成交量 * vol_multiple
       —— 上涨波段定义为 [T, today] 间的所有交易日（不做趋势单调性强约束，稳健且可复现）
    3) 近 ma60_slope_days（默认 5）个交易日的 MA60 回归斜率 > 0
    """

    def __init__(
        self,
        *,
        lookback_n: int = 60,
        vol_multiple: float = 1.5,
        j_threshold: float = -5.0,
        j_q_threshold: float = 0.10,
        ma60_slope_days: int = 5,
        max_window: int = 120,  # 用于计算 J 分位
    ) -> None:
        if lookback_n < 2:
            raise ValueError("lookback_n 应 ≥ 2")
        if not (0.0 <= j_q_threshold <= 1.0):
            raise ValueError("j_q_threshold 应位于 [0,1]")
        if ma60_slope_days < 2:
            raise ValueError("ma60_slope_days 应 ≥ 2")
        self.lookback_n = lookback_n
        self.vol_multiple = vol_multiple
        self.j_threshold = j_threshold
        self.j_q_threshold = j_q_threshold
        self.ma60_slope_days = ma60_slope_days
        self.max_window = max_window

    @staticmethod
    def _ma_slope_positive(series: pd.Series, days: int) -> bool:
        """对最近 days 个点做一阶线性回归，斜率 > 0 判为正"""
        seg = series.dropna().tail(days)
        if len(seg) < days:
            return False
        x = np.arange(len(seg), dtype=float)
        # 线性回归（最小二乘）：斜率 k
        k, _ = np.polyfit(x, seg.values.astype(float), 1)
        return bool(k > 0)

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        """
        hist：按日期升序，最后一行是目标交易日
        需包含列：date, open, high, low, close, volume
        """
        if hist.empty:
            return False

        hist = hist.copy().sort_values("date")
        # 至少要有 60 日用于 MA60，再加 lookback/slope 的缓冲
        min_len = max(60 + self.lookback_n + self.ma60_slope_days, self.max_window + 5)
        if len(hist) < min_len:
            return False

        if not passes_day_constraints_today(hist):
            return False

        # --- 计算指标 ---
        kdj = compute_kdj(hist)
        j_today = float(kdj["J"].iloc[-1])
        j_window = kdj["J"].tail(self.max_window).dropna()
        if j_window.empty:
            return False
        j_q_val = float(j_window.quantile(self.j_q_threshold))

        # 1) 当日 J 绝对低或相对低
        if not (j_today < self.j_threshold or j_today <= j_q_val):
            return False

        # 2) MA60 及有效上穿（使用通用函数）
        hist["MA60"] = hist["close"].rolling(window=60, min_periods=1).mean()
        if hist["close"].iloc[-1] < hist["MA60"].iloc[-1]:
            return False

        t_pos = last_valid_ma_cross_up(hist["close"], hist["MA60"], lookback_n=self.lookback_n)
        if t_pos is None:
            return False

        # ===[T, today] 内以 High 最大值的交易日为 Tmax ===
        seg_T_to_today = hist.iloc[t_pos:]
        if seg_T_to_today.empty:
            return False

        # 若并列最高，默认取“第一次”出现的那天；要“最后一次”可改见注释
        tmax_label = seg_T_to_today["high"].idxmax()
        int_pos_T = t_pos
        int_pos_Tmax = hist.index.get_loc(tmax_label)

        if int_pos_Tmax < int_pos_T:
            return False

        # 上涨波段 [T, Tmax]（含端点）
        wave = hist.iloc[int_pos_T : int_pos_Tmax + 1]
        wave_len = len(wave)
        if wave_len < 3:
            return False

        # 等长前置窗口 [T - wave_len, T-1]
        pre_start_pos = max(0, int_pos_T - min(wave_len, 10))
        pre = hist.iloc[pre_start_pos:int_pos_T]
        if len(pre) < max(5, min(10, wave_len)):
            return False

        # 成交量均值对比
        wave_avg_vol = float(wave["volume"].replace(0, np.nan).dropna().mean())
        pre_avg_vol = float(pre["volume"].replace(0, np.nan).dropna().mean())
        if not (np.isfinite(wave_avg_vol) and np.isfinite(pre_avg_vol) and pre_avg_vol > 0):
            return False

        if wave_avg_vol < self.vol_multiple * pre_avg_vol:
            return False

        # 3) MA60 斜率 > 0（保留原实现）
        if not self._ma_slope_positive(hist["MA60"], self.ma60_slope_days):
            return False

        return zx_condition_at_positions(
            hist, require_close_gt_long=True, require_short_gt_long=True, pos=None
        )

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        # 给足 60 日均线与量能比较的历史长度
        need_len = max(60 + self.lookback_n + self.ma60_slope_days, self.max_window + 20)
        for code, df in data.items():
            hist = df[df["date"] <= date].tail(need_len)
            if len(hist) < need_len:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
