from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stock_trade_z.core.compute import (
    compute_kdj,
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from stock_trade_z.core.parallel_utils import parallel_select_helper

from .bbi_kdj import BBIKDJSelector


class SuperB1Selector:
    """SuperB1 选股器

    过滤逻辑概览
    ----------------
    1. **历史匹配 (t_m)** — 在 *lookback_n* 个交易日窗口内，至少存在一日
       满足 :class:`BBIKDJSelector`。

    2. **盘整区间** — 区间 ``[t_m, date-1]`` 收盘价波动率不超过 ``close_vol_pct``。

    3. **当日下跌** — ``(close_{date-1} - close_date) / close_{date-1}``
       ≥ ``price_drop_pct``。

    4. **J 值极低** — ``J < j_threshold`` *或* 位于历史 ``j_q_threshold`` 分位。
    """

    # ---------------------------------------------------------------------
    # 构造函数
    # ---------------------------------------------------------------------
    def __init__(
        self,
        *,
        lookback_n: int = 60,
        close_vol_pct: float = 0.05,
        price_drop_pct: float = 0.03,
        j_threshold: float = -5,
        j_q_threshold: float = 0.10,
        # ↓↓↓ 新增：嵌套 BBIKDJSelector 配置
        B1_params: dict[str, Any] | None = None,
    ) -> None:
        # ---------- 参数合法性检查 ----------
        if lookback_n < 2:
            raise ValueError("lookback_n 应 ≥ 2")
        if not (0 < close_vol_pct < 1):
            raise ValueError("close_vol_pct 应位于 (0, 1) 区间")
        if not (0 < price_drop_pct < 1):
            raise ValueError("price_drop_pct 应位于 (0, 1) 区间")
        if not (0 <= j_q_threshold <= 1):
            raise ValueError("j_q_threshold 应位于 [0, 1] 区间")
        if B1_params is None:
            raise ValueError("bbi_params没有给出")

        # ---------- 基本参数 ----------
        self.lookback_n = lookback_n
        self.close_vol_pct = close_vol_pct
        self.price_drop_pct = price_drop_pct
        self.j_threshold = j_threshold
        self.j_q_threshold = j_q_threshold

        # ---------- 内部 BBIKDJSelector ----------
        self.bbi_selector = BBIKDJSelector(**(B1_params or {}))

        # 为保证给 BBIKDJSelector 提供足够历史，预留额外缓冲
        self._extra_for_bbi = self.bbi_selector.max_window + 20

    # 单支股票过滤核心
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if len(hist) < 2:
            return False

        # —— 新增：所有战法统一当日过滤
        if not passes_day_constraints_today(hist):
            return False

        # ---------- Step-0: 数据量判断 ----------
        if len(hist) < self.lookback_n + self._extra_for_bbi:
            return False

        # ---------- Step-1: 搜索满足 BBIKDJ 的 t_m ----------
        lb_hist = hist.tail(self.lookback_n + 1)  # +1 以排除自身
        tm_idx: int | None = None
        for idx in lb_hist.index[:-1]:
            if self.bbi_selector._passes_filters(hist.loc[:idx]):
                tm_idx = idx
                stable_seg = hist.loc[tm_idx : hist.index[-2], "close"]
                if len(stable_seg) < 3:
                    tm_idx = None
                    break
                high, low = stable_seg.max(), stable_seg.min()
                if low <= 0 or (high / low - 1) > self.close_vol_pct:
                    tm_idx = None
                    continue
                break
        if tm_idx is None:
            return False

        # —— 新增：在 t_m 当日检查【收盘>长期线 且 短期线>长期线】
        tm_pos = hist.index.get_loc(tm_idx)
        if not zx_condition_at_positions(
            hist, require_close_gt_long=True, require_short_gt_long=True, pos=tm_pos
        ):
            return False

        # ---------- Step-3: 当日相对前一日跌幅 ----------
        close_today, close_prev = hist["close"].iloc[-1], hist["close"].iloc[-2]
        if close_prev <= 0 or (close_prev - close_today) / close_prev < self.price_drop_pct:
            return False

        # ---------- Step-4: J 值极低 ----------
        kdj = compute_kdj(hist)
        j_today = float(kdj["J"].iloc[-1])
        j_window = kdj["J"].iloc[-self.lookback_n :].dropna()
        j_q_val = float(j_window.quantile(self.j_q_threshold)) if not j_window.empty else np.nan
        if not (j_today < self.j_threshold or j_today <= j_q_val):
            return False

        # —— 当日仅要求【短期线>长期线】
        return zx_condition_at_positions(
            hist, require_close_gt_long=False, require_short_gt_long=True, pos=None
        )

    # 批量选股接口
    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        min_len = self.lookback_n + self._extra_for_bbi
        for code, df in data.items():
            hist = df[df["date"] <= date].tail(min_len)
            if len(hist) < min_len:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
