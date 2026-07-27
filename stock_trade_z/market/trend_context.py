"""Load Zhitu pool snapshots from disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from stock_trade_z.market.fetch_trend import POOL_NAMES, _normalize_pool_df, _normalize_trade_date


@dataclass
class TrendContext:
    trade_date: pd.Timestamp
    pools: dict[str, pd.DataFrame]

    def symbols_in(self, *pool_names: str) -> set[str]:
        symbols: set[str] = set()
        for name in pool_names:
            df = self.pools.get(name)
            if df is None or df.empty or "symbol" not in df.columns:
                continue
            symbols.update(df["symbol"].astype(str).str.zfill(6).tolist())
        return symbols

    def row_for(self, symbol: str, pool_name: str) -> pd.Series | None:
        df = self.pools.get(pool_name)
        if df is None or df.empty:
            return None
        sym = str(symbol).zfill(6)
        matched = df[df["symbol"].astype(str).str.zfill(6) == sym]
        if matched.empty:
            return None
        return matched.iloc[0]

    def pool_for_symbol(self, symbol: str) -> str | None:
        sym = str(symbol).zfill(6)
        for name in POOL_NAMES:
            df = self.pools.get(name)
            if df is None or df.empty:
                continue
            if sym in df["symbol"].astype(str).str.zfill(6).values:
                return name
        return None

    def meta_for(self, symbol: str) -> dict:
        sym = str(symbol).zfill(6)
        for name in POOL_NAMES:
            row = self.row_for(sym, name)
            if row is not None:
                meta = row.to_dict()
                meta["pool"] = name
                return meta
        return {}


def _date_dir_name(trade_date: str) -> str:
    return pd.to_datetime(_normalize_trade_date(trade_date)).strftime("%Y-%m-%d")


def _read_pool_csv(path: Path) -> pd.DataFrame:
    """Read a pool snapshot CSV; empty files are treated as an empty pool."""
    if path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return _normalize_pool_df(pd.read_csv(path))
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_trend_context(trend_dir: Path, trade_date: str | None = None) -> TrendContext:
    if trade_date is None:
        subdirs = sorted([p for p in trend_dir.iterdir() if p.is_dir()], reverse=True)
        if not subdirs:
            raise FileNotFoundError(f"no trend date folders under {trend_dir}")
        date_dir = subdirs[0]
        trade_ts = pd.to_datetime(date_dir.name)
    else:
        date_dir = trend_dir / _date_dir_name(trade_date)
        trade_ts = pd.to_datetime(_normalize_trade_date(trade_date))
        if not date_dir.exists():
            raise FileNotFoundError(f"trend folder not found: {date_dir}")

    pools: dict[str, pd.DataFrame] = {}
    for name in POOL_NAMES:
        path = date_dir / f"{name}.csv"
        if path.exists():
            pools[name] = _read_pool_csv(path)
        else:
            pools[name] = pd.DataFrame()

    return TrendContext(trade_date=trade_ts, pools=pools)


def pool_symbols_from_dir(trend_dir: Path, trade_date: str | None = None) -> list[str]:
    ctx = load_trend_context(trend_dir, trade_date)
    return sorted(ctx.symbols_in(*POOL_NAMES))
