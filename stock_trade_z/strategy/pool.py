"""Pool-specific selectors for qsgc / ztgc (not normal K-line战法)."""

from __future__ import annotations

from datetime import time

import pandas as pd

from stock_trade_z.market.fetch_trend import _parse_yes_flag


def _parse_hms(value) -> time | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 3:
        return None
    try:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _pool_symbols(pool_df: pd.DataFrame) -> list[str]:
    if pool_df is None or pool_df.empty or "symbol" not in pool_df.columns:
        return []
    return pool_df["symbol"].astype(str).str.zfill(6).tolist()


class EarlySealSelector:
    """涨停池：早盘封板、无炸板。"""

    def __init__(self, pool: str = "ztgc", max_fbt: str = "10:00:00", max_zbc: int = 0) -> None:
        self.pool = pool
        self.max_fbt = _parse_hms(max_fbt) or time(10, 0)
        self.max_zbc = max_zbc

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        picks: list[str] = []
        for _, row in pool_df.iterrows():
            sym = str(row["symbol"]).zfill(6)
            fbt = _parse_hms(row.get("fbt"))
            zbc = int(row.get("zbc", 0) or 0)
            if fbt is None or fbt > self.max_fbt:
                continue
            if zbc > self.max_zbc:
                continue
            if sym in data:
                picks.append(sym)
        return picks


class ContinuationBoardSelector:
    """涨停池：连板延续。"""

    def __init__(self, pool: str = "ztgc", min_lbc: int = 2, max_zbc: int = 1) -> None:
        self.pool = pool
        self.min_lbc = min_lbc
        self.max_zbc = max_zbc

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        picks: list[str] = []
        for _, row in pool_df.iterrows():
            sym = str(row["symbol"]).zfill(6)
            lbc = int(row.get("lbc", 0) or 0)
            zbc = int(row.get("zbc", 0) or 0)
            if lbc < self.min_lbc or zbc > self.max_zbc:
                continue
            if sym in data:
                picks.append(sym)
        return picks


class FirstBoardLeaderSelector:
    """涨停池：首板龙头。"""

    def __init__(
        self,
        pool: str = "ztgc",
        max_fbt: str = "10:30:00",
        hs_min: float = 3.0,
        hs_max: float = 25.0,
    ) -> None:
        self.pool = pool
        self.max_fbt = _parse_hms(max_fbt) or time(10, 30)
        self.hs_min = hs_min
        self.hs_max = hs_max

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        picks: list[str] = []
        for _, row in pool_df.iterrows():
            sym = str(row["symbol"]).zfill(6)
            lbc = int(row.get("lbc", 0) or 0)
            fbt = _parse_hms(row.get("fbt"))
            hs = float(row.get("hs", 0) or 0)
            if lbc != 1:
                continue
            if fbt is None or fbt > self.max_fbt:
                continue
            if not (self.hs_min <= hs <= self.hs_max):
                continue
            if sym in data:
                picks.append(sym)
        return picks


class NewHighMomentumSelector:
    """强势股池：新高 + 涨速 + 量比。"""

    def __init__(self, pool: str = "qsgc", min_zs: float = 1.0, min_lb: float = 1.5) -> None:
        self.pool = pool
        self.min_zs = min_zs
        self.min_lb = min_lb

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        picks: list[str] = []
        for _, row in pool_df.iterrows():
            sym = str(row["symbol"]).zfill(6)
            nh = _parse_yes_flag(row.get("nh", 0))
            zs = float(row.get("zs", 0) or 0)
            lb = float(row.get("lb", 0) or 0)
            if nh != 1 or zs < self.min_zs or lb < self.min_lb:
                continue
            if sym in data:
                picks.append(sym)
        return picks


class NearLimitMomentumSelector:
    """强势股池：贴近涨停价且涨幅可观。"""

    def __init__(
        self, pool: str = "qsgc", max_dist_to_limit: float = 0.02, min_zf: float = 5.0
    ) -> None:
        self.pool = pool
        self.max_dist_to_limit = max_dist_to_limit
        self.min_zf = min_zf

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        picks: list[str] = []
        for _, row in pool_df.iterrows():
            sym = str(row["symbol"]).zfill(6)
            price = float(row.get("p", 0) or 0)
            ztp = float(row.get("ztp", 0) or 0)
            zf = float(row.get("zf", 0) or 0)
            if price <= 0 or ztp <= 0 or zf < self.min_zf:
                continue
            dist = (ztp - price) / ztp
            if dist > self.max_dist_to_limit:
                continue
            if sym in data:
                picks.append(sym)
        return picks


class VolumeBreakoutSelector:
    """强势股池：高换手 + K线放量。"""

    def __init__(
        self,
        pool: str = "qsgc",
        hs_min: float = 5.0,
        vol_lookback: int = 5,
        vol_multiple: float = 1.5,
    ) -> None:
        self.pool = pool
        self.hs_min = hs_min
        self.vol_lookback = vol_lookback
        self.vol_multiple = vol_multiple

    def select(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pools: dict[str, pd.DataFrame],
    ) -> list[str]:
        pool_df = pools.get(self.pool, pd.DataFrame())
        picks: list[str] = []
        for _, row in pool_df.iterrows():
            sym = str(row["symbol"]).zfill(6)
            hs = float(row.get("hs", 0) or 0)
            if hs < self.hs_min:
                continue
            hist = data.get(sym)
            if hist is None or hist.empty:
                continue
            hist = hist[hist["date"] <= date].tail(self.vol_lookback + 1)
            if len(hist) < self.vol_lookback + 1:
                continue
            today_vol = float(hist["volume"].iloc[-1])
            avg_vol = float(hist["volume"].iloc[:-1].mean())
            if avg_vol <= 0 or today_vol < avg_vol * self.vol_multiple:
                continue
            picks.append(sym)
        return picks
