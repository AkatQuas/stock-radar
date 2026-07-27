from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


# ---------------------- 通用CCI计算函数（复用逻辑） ----------------------
def compute_cci(typ_series: pd.Series, period: int):
    """
    计算指定周期的CCI指标
    typ_series: 典型价格序列（TYP=(high+low+close)/3）
    period: CCI计算周期（如14、84）
    """
    # 计算周期内的移动平均
    typ_ma = typ_series.rolling(window=period).mean()

    # 计算周期内的平均绝对偏差
    def avg_dev(x):
        return np.mean(np.abs(x - np.mean(x)))

    typ_avedev = typ_series.rolling(window=period).apply(avg_dev, raw=True)
    # CCI核心公式
    cci = (typ_series - typ_ma) / (0.015 * typ_avedev)
    return cci.round(2)


def compute_cci14_cci84(df: pd.DataFrame):
    """
    计算CCI14（14日商品通道指数）和CCI84（84日商品通道指数）指标
    df: 日线数据，需包含 open, high, low, close 列
    返回值：添加了CCI14、CCI84列的DataFrame
    """
    # 第一步：计算典型价格TYP=(high+low+close)/3
    df["TYP"] = (df["high"] + df["low"] + df["close"]) / 3

    # 第二步：调用通用函数计算CCI14和CCI84
    df["CCI14"] = compute_cci(df["TYP"], period=14)
    df["CCI84"] = compute_cci(df["TYP"], period=84)
    return df.drop(columns=["TYP"], errors="ignore")


# --------------------------- 通用指标 --------------------------- #
def compute_pit_and_trap(
    df: pd.DataFrame,
    gold_pit_threshold: float = -10.0,
    top_trap_threshold: float = 10.0,
):
    """
    计算黄金坑指标
    df: 日线数据，需包含 open, high, low, close 列
    返回值：添加了黄金坑
    """
    # RR8: 27日收盘价均线
    # RR9: 收盘价相对27日均线的偏离率
    # RRA: RR9的2日均线
    df = df.assign(RR8=df["close"].rolling(window=27, min_periods=1).mean())
    df = df.assign(RR9=(df["close"] - df["RR8"]) / df["RR8"] * 100)
    df = df.assign(RRA=df["RR9"].rolling(window=2, min_periods=1).mean())

    # 黄金坑计算方式 1
    # # RRB: 上一次RRA从 gold_pit_threshold 下方上穿 gold_pit_threshold 的周期数
    # cross_up = ((df['RRA'].shift(1) < gold_pit_threshold) & (df['RRA'] > gold_pit_threshold)).astype(int)
    # df['RRB'] = cross_up[::-1].cumsum()[::-1].cumsum()
    # df['RRB'] = df['RRB'].where(cross_up == 1, np.nan).bfill().fillna(10000)

    # # RRD: 黄金坑信号条件，满足则输出-120，否则0
    # df['RRD'] = ((df['RRA'] < -10) & (df['RRB'] > 3)).astype(int)
    # df['gold_pit'] = np.where(df['RRD'] == 1, -120, 0)

    # 黄金坑计算方式 2
    # Step1: 标记RRA上穿 gold_pit_threshold 的信号行（1=信号，0=无信号）
    # CROSS(gold_pit_threshold, RRA) 等价于 RRA从< gold_pit_threshold 变为 > gold_pit_threshold
    df = df.assign(
        cross_up_signal=(
            (df["RRA"].shift(1) < gold_pit_threshold) & (df["RRA"] >= gold_pit_threshold)
        ).astype(int)
    )

    # Step2: 计算BARSLAST - 距离上一次信号的周期数（对齐同花顺逻辑）
    df = df.assign(RRB=np.nan)  # 初始化
    last_signal_idx = None  # 记录上一次信号的位置

    for i in range(len(df)):
        # 如果当前行是信号行，重置周期数为0
        if df.loc[i, "cross_up_signal"] == 1:
            last_signal_idx = i
            df.loc[i, "RRB"] = 0
        # 如果有历史信号，计算当前到信号的周期数
        elif last_signal_idx is not None:
            df.loc[i, "RRB"] = i - last_signal_idx
        # 无历史信号时，RRB为NaN（或设为大数，保持原逻辑）
        else:
            df.loc[i, "RRB"] = 10000  # 无信号时设为大数，避免条件误触发

    # 黄金坑信号条件：RRA < -10 且 距离上一次上穿超过3个周期
    df = df.assign(gold_pit=np.where((df["RRA"] < gold_pit_threshold) & (df["RRB"] > 3), -120, 0))

    # Step 2: Mark RRA cross DOWN the top trap threshold (e.g., 10)
    # Cross down = RRA shifts from > threshold to < threshold
    df = df.assign(
        cross_down_signal=(
            (df["RRA"].shift(1) > top_trap_threshold) & (df["RRA"] < top_trap_threshold)
        ).astype(int)
    )

    # Step 3: Calculate RRC (BARSLAST - distance from last cross down)
    df = df.assign(RRC=np.nan)  # 初始化
    last_down_signal_idx: int | None = None

    for i in range(len(df)):
        if df.loc[i, "cross_down_signal"] == 1:
            last_down_signal_idx = i
            df.loc[i, "RRC"] = 0
        elif last_down_signal_idx is not None:
            df.loc[i, "RRC"] = i - last_down_signal_idx
        else:
            df.loc[i, "RRC"] = 10000  # No prior signal = large value

    # Step 4: Top Trap sell signal (120 = sell, 0 = no)
    # Logic: RRA > threshold AND distance from last cross down > 3 periods
    df = df.assign(
        top_trap_sell=np.where((df["RRA"] > top_trap_threshold) & (df["RRC"] > 3), 120, 0)
    )

    # 删除中间计算列（可选，如需保留可注释）
    return df.drop(
        columns=[
            "RR8",
            "RR9",
            "cross_up_signal",
            "RRA",
            "RRB",
            "cross_down_signal",
            "RRC",
            "RRD",
        ],
        errors="ignore",
    )


def compute_kdj(df: pd.DataFrame, n: int = 9) -> pd.DataFrame:
    if df.empty:
        return df.assign(K=np.nan, D=np.nan, J=np.nan)

    low_n = df["low"].rolling(window=n, min_periods=1).min()
    high_n = df["high"].rolling(window=n, min_periods=1).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 1e-9) * 100

    K = np.zeros_like(rsv, dtype=float)
    D = np.zeros_like(rsv, dtype=float)
    for i in range(len(df)):
        if i == 0:
            K[i] = D[i] = 50.0
        else:
            K[i] = 2 / 3 * K[i - 1] + 1 / 3 * rsv.iloc[i]
            D[i] = 2 / 3 * D[i - 1] + 1 / 3 * K[i]
    J = 3 * K - 2 * D
    return df.assign(K=K, D=D, J=J)


def compute_rsi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    close = df["close"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=n, min_periods=1).mean()
    avg_loss = loss.rolling(window=n, min_periods=1).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - 100 / (1 + rs)


def compute_bbi(df: pd.DataFrame) -> pd.Series:
    ma3 = df["close"].rolling(3).mean()
    ma6 = df["close"].rolling(6).mean()
    ma12 = df["close"].rolling(12).mean()
    ma24 = df["close"].rolling(24).mean()
    return (ma3 + ma6 + ma12 + ma24) / 4


def compute_rsv(
    df: pd.DataFrame,
    n: int,
) -> pd.Series:
    """
    按公式：RSV(N) = 100 × (C - LLV(L,N)) ÷ (HHV(C,N) - LLV(L,N))
    - C 用收盘价最高值 (HHV of close)
    - L 用最低价最低值 (LLV of low)
    """
    low_n = df["low"].rolling(window=n, min_periods=1).min()
    high_close_n = df["close"].rolling(window=n, min_periods=1).max()
    return (df["close"] - low_n) / (high_close_n - low_n + 1e-9) * 100.0


def compute_dif(df: pd.DataFrame, fast: int = 12, slow: int = 26) -> pd.Series:
    """计算 MACD 指标中的 DIF (EMA fast - EMA slow)。"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    return ema_fast - ema_slow


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Return DIF, DEA (signal), and MACD histogram columns."""
    dif = compute_dif(df, fast=fast, slow=slow)
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return pd.DataFrame({"DIF": dif, "DEA": dea, "MACD": hist})


def compute_bollinger(df: pd.DataFrame, n: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger bands: middle (SMA), upper, lower."""
    mid = df["close"].rolling(window=n, min_periods=n).mean()
    std = df["close"].rolling(window=n, min_periods=n).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return pd.DataFrame({"BB_MID": mid, "BB_UPPER": upper, "BB_LOWER": lower})


def compute_roc(close: pd.Series, n: int = 20) -> pd.Series:
    """Rate of change (%) over n periods: (C / C_{t-n} - 1) * 100."""
    prev = close.shift(n)
    return (close / prev - 1.0) * 100.0


def bbi_deriv_uptrend(
    bbi: pd.Series,
    *,
    min_window: int,
    max_window: int | None = None,
    q_threshold: float = 0.0,
) -> bool:
    """
    判断 BBI 是否“整体上升”。

    令最新交易日为 T，在区间 [T-w+1, T]（w 自适应，w ≥ min_window 且 ≤ max_window）
    内，先将 BBI 归一化：BBI_norm(t) = BBI(t) / BBI(T-w+1)。

    再计算一阶差分 Δ(t) = BBI_norm(t) - BBI_norm(t-1)。
    若 Δ(t) 的前 q_threshold 分位数 ≥ 0，则认为该窗口通过；只要存在
    **最长** 满足条件的窗口即可返回 True。q_threshold=0 时退化为
    “全程单调不降”（旧版行为）。

    Parameters
    ----------
    bbi : pd.Series
        BBI 序列（最新值在最后一位）。
    min_window : int
        检测窗口的最小长度。
    max_window : int | None
        检测窗口的最大长度；None 表示不设上限。
    q_threshold : float, default 0.0
        允许一阶差分为负的比例（0 ≤ q_threshold ≤ 1）。
    """
    if not 0.0 <= q_threshold <= 1.0:
        raise ValueError("q_threshold 必须位于 [0, 1] 区间内")

    bbi = bbi.dropna()
    if len(bbi) < min_window:
        return False

    longest = min(len(bbi), max_window or len(bbi))

    # 自最长窗口向下搜索，找到任一满足条件的区间即通过
    for w in range(longest, min_window - 1, -1):
        seg = bbi.iloc[-w:]  # 区间 [T-w+1, T]
        norm = seg / seg.iloc[0]  # 归一化
        diffs = np.diff(norm.values)  # 一阶差分
        if np.quantile(diffs, q_threshold) >= 0:
            return True
    return False


def find_peaks_in_series(
    df: pd.DataFrame,
    *,
    column: str = "high",
    distance: None | int = None,
    prominence: None | float = None,
    height: None | float = None,
    width: None | float = None,
    rel_height: float = 0.5,
    **kwargs: Any,
) -> pd.DataFrame:

    if column not in df.columns:
        raise KeyError(f"'{column}' not found in DataFrame columns: {list(df.columns)}")

    y = df[column].to_numpy()

    indices, props = find_peaks(
        y,
        distance=distance,
        prominence=prominence,
        height=height,
        width=width,
        rel_height=rel_height,
        **kwargs,
    )

    peaks_df = df.iloc[indices].copy()
    peaks_df["is_peak"] = True

    # Flatten SciPy arrays into columns (only those with same length as indices)
    for key, arr in props.items():
        if isinstance(arr, (list, np.ndarray)) and len(arr) == len(indices):
            peaks_df[f"peak_{key}"] = arr

    return peaks_df


def last_valid_ma_cross_up(
    close: pd.Series,
    ma: pd.Series,
    lookback_n: int | None = None,
) -> None | int:
    """
    查找“有效上穿 MA”的最后一个交易日 T（close[T-1] < ma[T-1] 且 close[T] ≥ ma[T]）。
    - 返回的是 **整数位置**（iloc 用）。
    - lookback_n: 仅在最近 N 根内查找；None 则全历史。
    """
    n = len(close)
    start = 1  # 至少要从 1 起，因为要看 T-1
    if lookback_n is not None:
        start = max(start, n - lookback_n)

    # 自后向前找最后一次有效上穿
    for i in range(n - 1, start - 1, -1):
        if i - 1 < 0:
            continue
        c_prev, c_now = close.iloc[i - 1], close.iloc[i]
        m_prev, m_now = ma.iloc[i - 1], ma.iloc[i]
        if (
            pd.notna(c_prev)
            and pd.notna(c_now)
            and pd.notna(m_prev)
            and pd.notna(m_now)
            and c_prev < m_prev
            and c_now >= m_now
        ):
            return i
    return None


def compute_zx_lines(
    df: pd.DataFrame, m1: int = 14, m2: int = 28, m3: int = 57, m4: int = 114
) -> tuple[pd.Series, pd.Series]:
    """返回 (ZXDQ, ZXDKX)
    ZXDQ = EMA(EMA(C,10),10)
    ZXDKX = (MA(C,14)+MA(C,28)+MA(C,57)+MA(C,114))/4
    """
    close = df["close"].astype(float)
    zxdq = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()

    ma1 = close.rolling(window=m1, min_periods=m1).mean()
    ma2 = close.rolling(window=m2, min_periods=m2).mean()
    ma3 = close.rolling(window=m3, min_periods=m3).mean()
    ma4 = close.rolling(window=m4, min_periods=m4).mean()
    zxdkx = (ma1 + ma2 + ma3 + ma4) / 4.0
    return zxdq, zxdkx


def passes_day_constraints_today(
    df: pd.DataFrame, pct_limit: float = 0.02, amp_limit: float = 0.07
) -> bool:
    """
    所有战法的统一当日过滤：
    1) 当前交易日相较于前一日涨跌幅 < pct_limit（绝对值）
    2) 当日振幅（High-Low 相对 Low） < amp_limit
    """
    if len(df) < 2:
        return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close_today = float(last["close"])
    close_yest = float(prev["close"])
    high_today = float(last["high"])
    low_today = float(last["low"])
    if close_yest <= 0 or low_today <= 0:
        return False
    pct_chg = abs(close_today / close_yest - 1.0)
    amplitude = (high_today - low_today) / low_today
    return (pct_chg < pct_limit) and (amplitude < amp_limit)


def zx_condition_at_positions(
    df: pd.DataFrame,
    *,
    require_close_gt_long: bool = True,
    require_short_gt_long: bool = True,
    pos: int | None = None,
) -> bool:
    """
    在指定位置 pos（iloc 位置；None 表示当日）检查知行条件：
      - 收盘 > 长期线（可选）
      - 短期线 > 长期线（可选）
    注：长期线需满样本；若为 NaN 直接返回 False。
    """
    if df.empty:
        return False
    zxdq, zxdkx = compute_zx_lines(df)
    if pos is None:
        pos = len(df) - 1

    if pos < 0 or pos >= len(df):
        return False

    short_line = float(zxdq.iloc[pos])
    long_line = float(zxdkx.iloc[pos]) if pd.notna(zxdkx.iloc[pos]) else float("nan")
    close_at_pos = float(df["close"].iloc[pos])

    if not np.isfinite(long_line) or not np.isfinite(short_line):
        return False

    close_ok = (not require_close_gt_long) or (close_at_pos > long_line)
    short_ok = (not require_short_gt_long) or (short_line > long_line)
    return close_ok and short_ok


def compute_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=n, min_periods=1).mean()
