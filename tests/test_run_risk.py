"""Unit tests for risk detection orchestration."""

from __future__ import annotations

import unittest

import pandas as pd

from stock_radar.strategy.base import RiskSelectorBase
from stock_radar.strategy.run_risk import RiskOptions, run_risk_detection


class _RiskFlag(RiskSelectorBase):
    min_history = 1

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def _passes_filters(self, hist: pd.DataFrame) -> bool:
        return True

    def select(self, date: pd.Timestamp, data: dict[str, pd.DataFrame], **ctx) -> list[str]:
        return [self.symbol] if self.symbol in data else []


class RunRiskTests(unittest.TestCase):
    def test_aggregates_hits_by_symbol(self):
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
        result = run_risk_detection(
            selectors={"a": _RiskFlag("600000"), "b": _RiskFlag("600000")},
            data=data,
            trade_date=date,
            stocklist=[{"symbol": "600000", "name": "浦发银行", "xueqiu_url": "https://x"}],
            opts=RiskOptions(),
        )
        self.assertEqual(result.aggregated["600000"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
