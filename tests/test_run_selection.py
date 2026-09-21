"""Unit tests for run_selection orchestration."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from stock_radar.strategy.base import SelectorBase
from stock_radar.strategy.run_selection import SelectionOptions, run_selection


class _PickOne(SelectorBase):
    min_history = 1

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        return True


class RunSelectionTests(unittest.TestCase):
    def test_runs_selector_and_returns_results(self):
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
        stocklist = [{"symbol": "600000", "name": "浦发银行", "xueqiu_url": "https://x"}]
        result = run_selection(
            selectors={"test": _PickOne()},
            data=data,
            trade_date=date,
            stocklist=stocklist,
            opts=SelectionOptions(track="normal"),
        )
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0]["stocks"][0]["symbol"], "600000")

    @patch("stock_radar.strategy.run_selection.analyze_picks", return_value="### 排序推荐\n- x")
    def test_llm_analyze_when_enabled(self, _analyze):
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
        stocklist = [{"symbol": "600000", "name": "浦发银行", "xueqiu_url": "https://x"}]
        result = run_selection(
            selectors={"test": _PickOne()},
            data=data,
            trade_date=date,
            stocklist=stocklist,
            opts=SelectionOptions(llm_analyze=True, track="normal"),
        )
        self.assertIsNotNone(result.llm_section)


if __name__ == "__main__":
    unittest.main()
