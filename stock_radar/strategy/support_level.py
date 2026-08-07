from __future__ import annotations

import numpy as np
import pandas as pd

from stock_radar.core.compute import (
    compute_atr,
    compute_rsi,
    find_peaks_in_series,
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from stock_radar.core.parallel_utils import parallel_select_helper


class SupportLevelSelector:
    def __init__(
        self,
        # ATR相关参数
        atr14_multiple: float = 2.0,
        atr7_pct_threshold: float = 1.2,
        window_high: int = 20,
        # RSI相关参数
        rsi_low: int = 30,
        rsi_high: int = 40,
        # 成交量参数
        vol_ratio: float = 0.7,
        use_zx_filter: bool = True,
    ):
        # 策略核心参数
        self.atr14_multiple = atr14_multiple
        self.atr7_pct_threshold = atr7_pct_threshold
        self.window_high = window_high
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.vol_ratio = vol_ratio
        self.use_zx_filter = use_zx_filter

    def _compute_strategy_indicators(self, hist: pd.DataFrame) -> pd.DataFrame:
        """
        计算策略所需的所有指标（封装为私有方法）
        :param hist: 单只股票的历史数据
        :return: 带所有指标的DataFrame
        """
        data = hist.copy()

        # 1. 计算ATR（复用工具函数）
        data["ATR14"] = compute_atr(data, n=14)
        data["ATR7"] = compute_atr(data, n=7)
        data["ATR7_pct"] = data["ATR7"] / data["close"] * 100

        # 2. 计算RSI（复用工具函数）
        data["RSI14"] = compute_rsi(data, n=14)
        data["RSI14_3d_mean"] = data["RSI14"].rolling(window=3).mean()

        # 3. 计算阶段高点（复用峰值检测函数）
        peaks_df = find_peaks_in_series(
            data,
            column="high",
            distance=self.window_high // 2,
            prominence=data["ATR14"].mean(),
        )
        # 填充阶段高点
        data["window_high"] = np.nan
        peak_indices = peaks_df.index
        for idx in data.index:
            prev_peaks = [p for p in peak_indices if p <= idx]
            if prev_peaks:
                data.loc[idx, "window_high"] = data.loc[max(prev_peaks), "high"]
        data["window_high"] = data["window_high"].fillna(
            data["high"].rolling(window=self.window_high).max()
        )

        # 4. 回落幅度（ATR14倍数）
        data["drop_from_high"] = (data["window_high"] - data["close"]) / data["ATR14"]

        # 5. 成交量指标
        data["vol_20d_mean"] = data["amount"].rolling(window=20).mean()
        data["vol_ratio"] = data["amount"] / data["vol_20d_mean"]

        # 6. 价格低位验证
        data["low_3d"] = data["low"].rolling(window=3).min()
        data["low_10d"] = data["low"].rolling(window=10).min()
        data["no_new_low"] = data["low_3d"] >= data["low_10d"] * 0.96

        # 7. 知行线过滤（复用工具函数）
        data["zx_filter"] = True
        if self.use_zx_filter:
            data["zx_filter"] = data.apply(
                lambda row: zx_condition_at_positions(
                    data.iloc[: data.index.get_loc(row.name) + 1]
                ),
                axis=1,
            )

        return data

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        """
        核心过滤逻辑：判断单只股票是否满足支撑位策略条件
        :param hist: 单只股票的历史数据
        :return: True=符合条件，False=不符合
        """
        # 空数据直接过滤
        if len(hist) < 30:  # 至少30根K线计算指标
            return False

        try:
            # 计算所有策略指标
            data = self._compute_strategy_indicators(hist)

            # 过滤条件1：当日波动约束（复用工具函数）
            if not passes_day_constraints_today(data):
                return False

            # 取最新一行数据（目标日期当天）
            latest = data.iloc[-1]

            # 过滤条件2：ATR回落幅度达标
            if latest["drop_from_high"] < self.atr14_multiple:
                return False

            # 过滤条件3：ATR7波动率收敛
            if latest["ATR7_pct"] > self.atr7_pct_threshold:
                return False

            # 过滤条件4：RSI低位企稳
            if (
                pd.isna(latest["RSI14_3d_mean"])
                or latest["RSI14"] < self.rsi_low
                or latest["RSI14_3d_mean"] < self.rsi_high
            ):
                return False

            # 过滤条件5：成交量缩量
            if pd.isna(latest["vol_ratio"]) or latest["vol_ratio"] > self.vol_ratio:
                return False

            # 过滤条件6：价格不创新低
            if not latest["no_new_low"]:
                return False

            # 过滤条件7：知行线趋势过滤（可选）
            return not (self.use_zx_filter and not latest["zx_filter"])

        except Exception as e:
            # 指标计算异常时，判定为不符合条件
            print(f"过滤逻辑执行异常：{e}")
            return False

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        for code, df in data.items():
            hist = df[df["date"] <= date]
            if hist.empty:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
