from __future__ import annotations

import pandas as pd

from stock_radar.core.compute import (
    compute_kdj,
    find_peaks_in_series,
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from stock_radar.core.parallel_utils import parallel_select_helper


class PeakKDJSelector:
    """
    Peaks + KDJ 选股器
    """

    def __init__(
        self,
        j_threshold: float = -5,
        max_window: int = 90,
        fluc_threshold: float = 0.03,
        gap_threshold: float = 0.02,
        j_q_threshold: float = 0.10,
    ) -> None:
        self.j_threshold = j_threshold
        self.max_window = max_window
        self.fluc_threshold = fluc_threshold  # 当日↔peak_(t-n) 波动率上限
        self.gap_threshold = gap_threshold  # oc_prev 必须高于区间最低收盘价的比例
        self.j_q_threshold = j_q_threshold

    # ---------- 单支股票过滤 ---------- #
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist.empty:
            return False

        if not passes_day_constraints_today(hist):
            return False

        hist = hist.copy().sort_values("date")
        hist["oc_max"] = hist[["open", "close"]].max(axis=1)

        # 1. 提取 peaks
        peaks_df = find_peaks_in_series(
            hist,
            column="oc_max",
            distance=6,
            prominence=0.5,
        )

        # 至少两个峰
        date_today = hist.iloc[-1]["date"]
        peaks_df = peaks_df[peaks_df["date"] < date_today]
        if len(peaks_df) < 2:
            return False

        peak_t = peaks_df.iloc[-1]  # 最新一个峰
        peaks_list = peaks_df.reset_index(drop=True)
        oc_t = peak_t.oc_max
        total_peaks = len(peaks_list)

        # 2. 回溯寻找 peak_(t-n)
        target_peak = None
        for idx in range(total_peaks - 2, -1, -1):
            peak_prev = peaks_list.loc[idx]
            oc_prev = peak_prev.oc_max
            if oc_t <= oc_prev:  # 要求 peak_t > peak_(t-n)
                continue

            # 只有当“总峰数 ≥ 3”时才检查区间内其他峰 oc_max
            if total_peaks >= 3 and idx < total_peaks - 2:
                inter_oc = peaks_list.loc[idx + 1 : total_peaks - 2, "oc_max"]
                if not (inter_oc < oc_prev).all():
                    continue

            # 新增： oc_prev 高于区间最低收盘价 gap_threshold
            date_prev = peak_prev.date
            mask = (hist["date"] > date_prev) & (hist["date"] < peak_t.date)
            min_close = hist.loc[mask, "close"].min()
            if pd.isna(min_close):
                continue  # 区间无数据
            if oc_prev <= min_close * (1 + self.gap_threshold):
                continue

            target_peak = peak_prev

            break

        if target_peak is None:
            return False

        # 3. 当日收盘价波动率
        close_today = hist.iloc[-1]["close"]
        fluc_pct = abs(close_today - target_peak.close) / target_peak.close
        if fluc_pct > self.fluc_threshold:
            return False

        # 4. KDJ 过滤
        kdj = compute_kdj(hist)
        j_today = float(kdj.iloc[-1]["J"])
        j_window = kdj["J"].tail(self.max_window).dropna()
        if j_window.empty:
            return False
        j_quantile = float(j_window.quantile(self.j_q_threshold))
        if not (j_today < self.j_threshold or j_today <= j_quantile):
            return False

        return zx_condition_at_positions(
            hist, require_close_gt_long=True, require_short_gt_long=True, pos=None
        )

    # ---------- 多股票批量 ---------- #
    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
    ) -> list[str]:
        tasks = []
        for code, df in data.items():
            hist = df[df["date"] <= date]
            if hist.empty:
                continue
            hist = hist.tail(self.max_window + 20)  # 额外缓冲
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
