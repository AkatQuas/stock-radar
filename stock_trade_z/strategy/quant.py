"""
Mainstream quantitative stock selection strategies.

Each selector exposes:
  - _passes_filters(hist: DataFrame) -> bool
  - select(date, data: Dict[str, DataFrame]) -> List[str]
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_trade_z.core.compute import (
    compute_bollinger,
    compute_macd,
    compute_roc,
    compute_rsi,
    last_valid_ma_cross_up,
    passes_day_constraints_today,
)
from stock_trade_z.core.parallel_utils import parallel_select_helper


class MomentumSelector:
    """
    Price momentum factor: ROC above threshold with trend filter (close > MA).

    Common in cross-sectional momentum / trend-following sleeves.
    """

    def __init__(
        self,
        roc_window: int = 20,
        roc_min_pct: float = 5.0,
        ma_window: int = 50,
        min_history: int = 60,
    ) -> None:
        self.roc_window = roc_window
        self.roc_min_pct = roc_min_pct
        self.ma_window = ma_window
        self.min_history = min_history

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or len(hist) < self.min_history:
            return False
        if not passes_day_constraints_today(hist):
            return False
        close = hist["close"].astype(float)
        roc = compute_roc(close, self.roc_window)
        ma = close.rolling(self.ma_window).mean()
        if pd.isna(roc.iloc[-1]) or pd.isna(ma.iloc[-1]):
            return False
        return float(roc.iloc[-1]) >= self.roc_min_pct and float(close.iloc[-1]) > float(
            ma.iloc[-1]
        )

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = [
            (code, df[df["date"] <= date].tail(self.min_history + 5))
            for code, df in data.items()
            if not df[df["date"] <= date].empty
        ]
        return parallel_select_helper(self, tasks)


class MACDGoldenCrossSelector:
    """MACD golden cross: DIF crosses above DEA recently, histogram turning up."""

    def __init__(
        self,
        lookback_n: int = 5,
        require_dif_positive: bool = True,
        min_history: int = 40,
    ) -> None:
        self.lookback_n = lookback_n
        self.require_dif_positive = require_dif_positive
        self.min_history = min_history

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or len(hist) < self.min_history:
            return False
        if not passes_day_constraints_today(hist):
            return False
        macd = compute_macd(hist)
        dif, dea = macd["DIF"], macd["DEA"]
        cross = last_valid_ma_cross_up(dif, dea, lookback_n=self.lookback_n)
        if cross is None:
            return False
        if self.require_dif_positive and float(dif.iloc[-1]) <= 0:
            return False
        hist_macd = float(macd["MACD"].iloc[-1])
        prev_macd = float(macd["MACD"].iloc[-2])
        return hist_macd > prev_macd

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = [
            (code, df[df["date"] <= date].tail(self.min_history + 10))
            for code, df in data.items()
            if len(df[df["date"] <= date]) >= self.min_history
        ]
        return parallel_select_helper(self, tasks)


class BollingerMeanReversionSelector:
    """
    Mean reversion: price at/below lower Bollinger band with RSI oversold.

    Classic short-term reversal setup (not risk detection).
    """

    def __init__(
        self,
        bb_window: int = 20,
        bb_std: float = 2.0,
        rsi_window: int = 14,
        rsi_max: float = 35.0,
        min_history: int = 30,
    ) -> None:
        self.bb_window = bb_window
        self.bb_std = bb_std
        self.rsi_window = rsi_window
        self.rsi_max = rsi_max
        self.min_history = min_history

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or len(hist) < self.min_history:
            return False
        if not passes_day_constraints_today(hist):
            return False
        bb = compute_bollinger(hist, n=self.bb_window, num_std=self.bb_std)
        rsi = compute_rsi(hist, n=self.rsi_window)
        close = float(hist["close"].iloc[-1])
        lower = float(bb["BB_LOWER"].iloc[-1])
        rsi_v = float(rsi.iloc[-1])
        if pd.isna(lower) or pd.isna(rsi_v):
            return False
        return close <= lower and rsi_v <= self.rsi_max

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = [
            (code, df[df["date"] <= date].tail(self.min_history + 5))
            for code, df in data.items()
            if len(df[df["date"] <= date]) >= self.min_history
        ]
        return parallel_select_helper(self, tasks)


class DonchianBreakoutSelector:
    """
    Donchian channel breakout: close breaks N-day high with volume confirmation.

    Turtle-trading style breakout; widely used in CTA trend systems.
    """

    def __init__(
        self,
        channel_n: int = 20,
        vol_lookback: int = 20,
        vol_multiple: float = 1.5,
        min_history: int = 25,
    ) -> None:
        self.channel_n = channel_n
        self.vol_lookback = vol_lookback
        self.vol_multiple = vol_multiple
        self.min_history = min_history

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or len(hist) < self.min_history:
            return False
        if not passes_day_constraints_today(hist):
            return False
        if len(hist) < self.channel_n + 2:
            return False
        prev_high = float(hist["high"].iloc[-(self.channel_n + 1) : -1].max())
        close_today = float(hist["close"].iloc[-1])
        if close_today <= prev_high:
            return False
        vol_today = float(hist["volume"].iloc[-1])
        vol_avg = (
            hist["volume"].iloc[-(self.vol_lookback + 1) : -1].replace(0, np.nan).dropna().mean()
        )
        if not np.isfinite(vol_avg) or vol_avg <= 0:
            return False
        return vol_today >= self.vol_multiple * vol_avg

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = [
            (code, df[df["date"] <= date].tail(self.min_history + 5))
            for code, df in data.items()
            if len(df[df["date"] <= date]) >= self.min_history
        ]
        return parallel_select_helper(self, tasks)


class DualMAGoldenCrossSelector:
    """Dual moving-average golden cross with price above both MAs."""

    def __init__(
        self,
        short_ma: int = 10,
        long_ma: int = 30,
        lookback_n: int = 5,
        min_history: int = 35,
    ) -> None:
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.lookback_n = lookback_n
        self.min_history = min_history

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        if hist is None or len(hist) < self.min_history:
            return False
        if not passes_day_constraints_today(hist):
            return False
        close = hist["close"].astype(float)
        ma_s = close.rolling(self.short_ma).mean()
        ma_l = close.rolling(self.long_ma).mean()
        cross = last_valid_ma_cross_up(ma_s, ma_l, lookback_n=self.lookback_n)
        if cross is None:
            return False
        c = float(close.iloc[-1])
        return c > float(ma_s.iloc[-1]) and c > float(ma_l.iloc[-1])

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame]) -> list[str]:
        tasks = [
            (code, df[df["date"] <= date].tail(self.min_history + 10))
            for code, df in data.items()
            if len(df[df["date"] <= date]) >= self.min_history
        ]
        return parallel_select_helper(self, tasks)
