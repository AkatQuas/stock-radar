"""Unit tests for unified Selector interface."""

from __future__ import annotations

import unittest

import pandas as pd

from stock_radar.strategy.base import (
    PoolSelectorBase,
    SelectorBase,
    VectorSelector,
    is_vector_selector,
    run_select,
)
from stock_radar.strategy.loader import load_pool_selectors
from stock_radar.strategy.pipeline import B1Selector, BrickChartSelector


class _AlwaysPick(SelectorBase):
    min_history = 1

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        return True


class _PoolPick(PoolSelectorBase):
    def _select_from_pool(
        self,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
        pool_df: pd.DataFrame,
    ) -> list[str]:
        return [
            str(row["symbol"]).zfill(6)
            for _, row in pool_df.iterrows()
            if str(row["symbol"]) in data
        ]


class SelectorBaseTests(unittest.TestCase):
    def test_run_select_kline(self):
        date = pd.Timestamp("2026-01-10")
        data = {
            "600000": pd.DataFrame(
                {
                    "date": [date],
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.5],
                    "volume": [1000],
                    "amount": [10500.0],
                    "pct_chg": [0.0],
                }
            )
        }
        picks = run_select(_AlwaysPick(), date, data)
        self.assertEqual(picks, ["600000"])

    def test_run_select_pool(self):
        date = pd.Timestamp("2026-01-10")
        data = {"600000": pd.DataFrame({"date": [date], "close": [10.0]})}
        pools = {"ztgc": pd.DataFrame({"symbol": ["600000"]})}
        picks = run_select(_PoolPick(pool="ztgc"), date, data, pools=pools)
        self.assertEqual(picks, ["600000"])

    def test_load_pool_selectors_via_registry(self):
        selectors = load_pool_selectors()
        self.assertEqual(len(selectors), 6)
        for selector in selectors.values():
            self.assertIsInstance(selector, PoolSelectorBase)

    def test_pipeline_selectors_are_vector_selectors(self):
        for sel in (B1Selector(), BrickChartSelector()):
            self.assertTrue(is_vector_selector(sel))
            self.assertIsInstance(sel, VectorSelector)

    def test_filter_selectors_are_not_vector_selectors(self):
        self.assertFalse(is_vector_selector(_AlwaysPick()))


if __name__ == "__main__":
    unittest.main()
