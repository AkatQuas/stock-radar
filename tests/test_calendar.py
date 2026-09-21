"""Unit tests for trading calendar (offline, injectable adapter)."""

from __future__ import annotations

import unittest

import pandas as pd

from stock_radar.market.calendar import is_trade_date


class FakeKlineSource:
    """In-memory K-line source for calendar tests."""

    def __init__(self, bars: dict[tuple[str, str], pd.DataFrame]) -> None:
        self._bars = bars

    def fetch_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        return self._bars.get((code, start), pd.DataFrame())


def _bar(date: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.to_datetime(date, format="%Y%m%d")],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [1000],
            "amount": [10500.0],
            "pct_chg": [0.0],
        }
    )


class TradeDateTests(unittest.TestCase):
    def test_trade_date_when_benchmark_has_bar(self):
        source = FakeKlineSource({("600000", "20260919"): _bar("20260919")})
        self.assertTrue(is_trade_date("2026-09-19", source=source))

    def test_non_trade_date_when_benchmark_empty(self):
        source = FakeKlineSource({})
        self.assertFalse(is_trade_date("2026-09-20", source=source))

    def test_today_alias_normalized(self):
        source = FakeKlineSource({("600000", "20260921"): _bar("20260921")})
        self.assertTrue(is_trade_date("today", source=source))


if __name__ == "__main__":
    unittest.main()
