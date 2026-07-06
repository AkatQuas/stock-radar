from typing import Any

import numpy as np
import pandas as pd

from .compute import (
    bbi_deriv_uptrend,
    compute_atr,
    compute_bbi,
    compute_cci14_cci84,
    compute_dif,
    compute_kdj,
    compute_pit_and_trap,
    compute_rsi,
    compute_rsv,
    compute_zx_lines,
    find_peaks_in_series,
    last_valid_ma_cross_up,
    passes_day_constraints_today,
    zx_condition_at_positions,
)
from .parallel_utils import parallel_select_helper


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


class GoldPitSelector:
    def __init__(
        self,
        gold_pit_threshold: float = -10.0,
        cci_overbought_threshold: float = 100.0,
        cci_extreme_overbought_threshold: float = 200.0,
        cci_oversold_threshold: float = -100.0,
    ) -> None:
        self.gold_pit_threshold = gold_pit_threshold
        self.cci_overbought_threshold = cci_overbought_threshold
        self.cci_extreme_overbought_threshold = cci_extreme_overbought_threshold
        self.cci_oversold_threshold = cci_oversold_threshold

    # ---------- 单支股票过滤 ---------- #
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if not passes_day_constraints_today(hist):
            return False
        hist = compute_pit_and_trap(hist, self.gold_pit_threshold)
        hist = compute_cci14_cci84(hist)
        # CCI Sell Signals (overbought)
        hist["cci14_overbought_sell"] = np.where(
            hist["CCI14"] > self.cci_overbought_threshold, 1, 0
        )
        hist["cci14_extreme_overbought_sell"] = np.where(
            hist["CCI14"] > self.cci_extreme_overbought_threshold, 1, 0
        )
        hist["cci84_overbought_sell"] = np.where(
            hist["CCI84"] > self.cci_overbought_threshold, 1, 0
        )

        # CCI Buy Signal (oversold, optional reference)
        hist["cci14_oversold_buy"] = np.where(hist["CCI14"] < self.cci_oversold_threshold, 1, 0)
        return bool(hist["cci14_oversold_buy"].iloc[-1] == 1 and hist["gold_pit"].iloc[-1] == -120)

    # ---------- 多股票批量 ---------- #
    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        for code, df in data.items():
            hist = df[df["date"] <= date]
            if hist.empty:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)


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


class BBIShortLongSelector:
    """
    BBI 上升 + 短/长期 RSV 条件 + DIF > 0 选股器
    """

    def __init__(
        self,
        n_short: int = 3,
        n_long: int = 21,
        m: int = 3,
        bbi_min_window: int = 90,
        max_window: int = 150,
        bbi_q_threshold: float = 0.05,
        upper_rsv_threshold: float = 75,
        lower_rsv_threshold: float = 25,
    ) -> None:
        if m < 2:
            raise ValueError("m 必须 ≥ 2")
        self.n_short = n_short
        self.n_long = n_long
        self.m = m
        self.bbi_min_window = bbi_min_window
        self.max_window = max_window
        self.bbi_q_threshold = bbi_q_threshold
        self.upper_rsv_threshold = upper_rsv_threshold
        self.lower_rsv_threshold = lower_rsv_threshold

    # ---------- 单支股票过滤 ---------- #
    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        hist = hist.copy()
        hist["BBI"] = compute_bbi(hist)

        if not passes_day_constraints_today(hist):
            return False

        # 1. BBI 上升（允许部分回撤）
        if not bbi_deriv_uptrend(
            hist["BBI"],
            min_window=self.bbi_min_window,
            max_window=self.max_window,
            q_threshold=self.bbi_q_threshold,
        ):
            return False

        # 2. 计算短/长期 RSV -----------------
        hist["RSV_short"] = compute_rsv(hist, self.n_short)
        hist["RSV_long"] = compute_rsv(hist, self.n_long)

        if len(hist) < self.m:
            return False  # 数据不足

        win = hist.iloc[-self.m :]  # 最近 m 天
        long_ok = (
            win["RSV_long"] >= self.upper_rsv_threshold
        ).all()  # 长期 RSV 全 ≥ upper_rsv_threshold

        short_series = win["RSV_short"]

        # 条件：从最近 m 天的第一天起，存在某天 i 满足 RSV_short[i] >= upper，
        # 且在该天之后（j > i）存在某天 j 满足 RSV_short[j] < lower
        mask_upper = short_series >= self.upper_rsv_threshold
        mask_lower = short_series < self.lower_rsv_threshold

        has_upper_then_lower = False
        if mask_upper.any():
            upper_indices = np.where(mask_upper.to_numpy())[0]
            for i in upper_indices:
                # 只检查 i 之后的日子
                if i + 1 < len(short_series) and mask_lower.iloc[i + 1 :].any():
                    has_upper_then_lower = True
                    break

        end_ok = short_series.iloc[-1] >= self.upper_rsv_threshold

        if not (long_ok and has_upper_then_lower and end_ok):
            return False

        # 3. MACD：DIF > 0 -------------------
        hist["DIF"] = compute_dif(hist)
        if hist["DIF"].iloc[-1] <= 0:
            return False

        # 4. 新增：知行情形
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
            # 预留足够长度：RSV 计算窗口 + BBI 检测窗口 + m
            need_len = max(self.n_short, self.n_long) + self.bbi_min_window + self.m
            hist = hist.tail(max(need_len, self.max_window))
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)


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


class BigBullishVolumeSelector:
    def __init__(
        self,
        *,
        up_pct_threshold: float = 0.04,  # 长阳阈值：例如 0.04 表示涨幅>4%
        upper_wick_pct_max: float = 0.5,  # 上影线比例上限（口径由 wick_mode 决定）
        vol_lookback_n: int = 20,  # 放量比较的历史天数 n
        vol_multiple: float = 1.5,  # 放量倍数阈值
        min_history: int | None = None,  # 最少历史长度（默认自动 = vol_lookback_n + 2）
        require_bullish_close: bool = True,  # 可选：要求当日收阳（close >= open）
        ignore_zero_volume: bool = True,  # 计算均量时是否忽略 volume=0
        close_lt_zxdq_mult: float = 1.0,  # 例如 1.0 表示 close < zxdq；1.02 表示 close < 1.02*zxdq
    ) -> None:
        if up_pct_threshold <= 0:
            raise ValueError("up_pct_threshold 应 > 0")
        if upper_wick_pct_max < 0:
            raise ValueError("upper_wick_pct_max 应 >= 0")
        if vol_lookback_n < 1:
            raise ValueError("vol_lookback_n 应 >= 1")
        if vol_multiple <= 0:
            raise ValueError("vol_multiple 应 > 0")
        if close_lt_zxdq_mult <= 0:
            raise ValueError("close_lt_zxdq_mult 应 > 0")

        self.up_pct_threshold = float(up_pct_threshold)
        self.upper_wick_pct_max = float(upper_wick_pct_max)
        self.vol_lookback_n = int(vol_lookback_n)
        self.vol_multiple = float(vol_multiple)
        self.require_bullish_close = bool(require_bullish_close)
        self.ignore_zero_volume = bool(ignore_zero_volume)
        self.close_lt_zxdq_mult = float(close_lt_zxdq_mult)
        self.eps = 1e-12
        self.min_history = (
            int(min_history) if min_history is not None else (self.vol_lookback_n + 2)
        )

    @staticmethod
    def _to_float(x) -> float:
        try:
            return float(x)
        except Exception:
            return float("nan")

    def _upper_wick_pct(self, o: float, h: float, c: float) -> float:
        return (h - max(o, c)) / max(o, c)

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or hist.empty:
            return False

        hist = hist.sort_values("date").copy()

        if len(hist) < self.min_history:
            return False
        if len(hist) < (self.vol_lookback_n + 2):
            return False  # 至少需要：T、T-1、以及 T-1 往前 n 天

        today = hist.iloc[-1]
        prev = hist.iloc[-2]

        oT = self._to_float(today.get("open"))
        hT = self._to_float(today.get("high"))
        lT = self._to_float(today.get("low"))
        cT = self._to_float(today.get("close"))
        vT = self._to_float(today.get("volume"))

        cP = self._to_float(prev.get("close"))

        # 基础合法性
        if not (
            np.isfinite(oT)
            and np.isfinite(hT)
            and np.isfinite(lT)
            and np.isfinite(cT)
            and np.isfinite(vT)
            and np.isfinite(cP)
        ):
            return False
        if cP <= 0 or cT <= 0:
            return False
        if hT < max(oT, cT) or lT > min(oT, cT):
            # K线数据异常（不一定必需，但建议保持严谨）
            return False

        # (可选) 要求当日收阳
        if self.require_bullish_close and not (cT >= oT):
            return False

        # 1) 长阳：涨幅 > 阈值
        pct_chg = cT / cP - 1.0
        if pct_chg <= self.up_pct_threshold:
            return False

        # 2) 上影线百分比 < 阈值
        wick_pct = self._upper_wick_pct(oT, hT, cT)
        if not np.isfinite(wick_pct):
            return False
        if wick_pct >= self.upper_wick_pct_max:
            return False

        # 3) 放量：当日成交量 > 前 n 日均量 * 倍数
        vol_hist = hist["volume"].iloc[-(self.vol_lookback_n + 1) : -1].astype(float)  # T-n ... T-1
        if self.ignore_zero_volume:
            vol_hist = vol_hist.replace(0, np.nan).dropna()

        if len(vol_hist) < max(3, int(self.vol_lookback_n * 0.6)):
            # 有效样本过少就不做判断（你也可以改成直接 False 或严格要求=vol_lookback_n）
            return False

        avg_vol = float(vol_hist.mean())
        if not (np.isfinite(avg_vol) and avg_vol > 0):
            return False

        if vT < self.vol_multiple * avg_vol:
            return False

        # 4) 偏离短线小于阈值
        try:
            zxdq, _ = compute_zx_lines(hist)
            zxdq_T = float(zxdq.iloc[-1])
        except Exception:
            zxdq_T = float("nan")

        if not np.isfinite(zxdq_T):
            return False
        return cT < zxdq_T * self.close_lt_zxdq_mult

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        need_len = max(self.min_history, self.vol_lookback_n + 2)
        for code, df in data.items():
            if df is None or df.empty:
                continue
            hist = df[df["date"] <= date].tail(need_len)
            if len(hist) < need_len:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)


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


class MACrossSelector:
    """
    Simple MA crossover strategy with volume confirmation

    Conditions:
    1. Short MA crosses above Long MA recently
    2. Price above both MAs
    3. Volume above average
    4. J value low (oversold)
    """

    def __init__(
        self,
        *,
        short_ma: int = 5,
        long_ma: int = 20,
        vol_multiple: float = 1.5,
        j_threshold: float = 15,
        lookback_n: int = 10,
    ) -> None:
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.vol_multiple = vol_multiple
        self.j_threshold = j_threshold
        self.lookback_n = lookback_n

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist.empty or len(hist) < max(self.long_ma, self.lookback_n) + 5:
            return False

        hist = hist.copy()

        # Day constraints
        if not passes_day_constraints_today(hist):
            return False

        # Calculate MAs
        hist["MA_short"] = hist["close"].rolling(window=self.short_ma).mean()
        hist["MA_long"] = hist["close"].rolling(window=self.long_ma).mean()

        # 1. Find recent crossover
        cross_pos = last_valid_ma_cross_up(
            hist["MA_short"], hist["MA_long"], lookback_n=self.lookback_n
        )
        if cross_pos is None:
            return False

        # 2. Price above both MAs
        close_today = hist["close"].iloc[-1]
        if close_today < hist["MA_short"].iloc[-1]:
            return False
        if close_today < hist["MA_long"].iloc[-1]:
            return False

        # 3. Volume confirmation
        vol_today = hist["volume"].iloc[-1]
        vol_avg = hist["volume"].tail(20).mean()
        if vol_today < vol_avg * self.vol_multiple:
            return False

        # 4. KDJ oversold
        kdj = compute_kdj(hist)
        return not kdj["J"].iloc[-1] > self.j_threshold

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = []
        need_len = max(self.long_ma, self.lookback_n) + 20
        for code, df in data.items():
            hist = df[df["date"] <= date].tail(need_len)
            if len(hist) < need_len:
                continue
            tasks.append((code, hist))

        return parallel_select_helper(self, tasks)
