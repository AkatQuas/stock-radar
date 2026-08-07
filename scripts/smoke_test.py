#!/usr/bin/env python3
"""Fast offline smoke test — used by pre-commit and CI."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_radar.market.load_stocklist import load_total_stocklist
from stock_radar.strategy import BBIKDJSelector, MomentumSelector, TurtleTradeSelector
from stock_radar.strategy.loader import load_pool_selectors, load_risk_selectors, load_selectors


def _sample_df(n: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 10 + np.cumsum(np.random.randn(n) * 0.05)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, n),
            "amount": np.random.randint(50_000_000, 200_000_000, n),
        }
    )


def main() -> None:
    selectors = load_selectors()
    risk = load_risk_selectors()
    pool = load_pool_selectors()
    if len(selectors) != 25:
        raise SystemExit(f"expected 25 selectors, got {len(selectors)}")
    if len(risk) != 8:
        raise SystemExit(f"expected 8 risk selectors, got {len(risk)}")
    if len(pool) != 6:
        raise SystemExit(f"expected 6 pool selectors, got {len(pool)}")

    df = _sample_df()
    for cls in (BBIKDJSelector, TurtleTradeSelector, MomentumSelector):
        cls()._passes_filters(df)

    if not load_total_stocklist():
        raise SystemExit("stocklist.total.csv is empty or missing")

    print("smoke test passed")


if __name__ == "__main__":
    main()
