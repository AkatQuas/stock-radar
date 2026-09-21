"""Trading calendar — probes A-share trading days via K-line adapter."""

from __future__ import annotations

import pandas as pd

from stock_radar.core.time import normalize_market_date
from stock_radar.market.tickflow_adapter import KlineSource, get_adapter

# Liquid A-share used to probe whether the market traded on a given day.
TRADE_DATE_BENCHMARK = "600000"


def is_trade_date(
    date: str | None = None,
    *,
    benchmark: str = TRADE_DATE_BENCHMARK,
    source: KlineSource | None = None,
) -> bool:
    """Return True when the K-line source has a daily bar for `date`."""
    adapter = source or get_adapter()
    target = normalize_market_date(date or "today")
    df = adapter.fetch_daily(benchmark, target, target)
    if df is None or df.empty:
        return False
    target_day = pd.to_datetime(target, format="%Y%m%d").normalize()
    return bool((df["date"].dt.normalize() == target_day).any())


def fetch_benchmark_daily(
    date: str,
    *,
    benchmark: str = TRADE_DATE_BENCHMARK,
    source: KlineSource | None = None,
) -> pd.DataFrame:
    """Fetch benchmark daily bars — used for trade-date diagnostics."""
    adapter = source or get_adapter()
    target = normalize_market_date(date)
    return adapter.fetch_daily(benchmark, target, target)
