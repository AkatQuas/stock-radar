"""TickFlow adapter — sole owner of vendor SDK seam."""

from __future__ import annotations

from typing import Protocol

import pandas as pd
from tickflow import TickFlow

from stock_radar.core.constant import COLUMNS, RateLimitError
from stock_radar.core.time import date_to_ms, normalize_market_date
from stock_radar.core.utils import looks_like_ip_ban, random_sleep_50_to_150ms
from stock_radar.market.load_stocklist import code2ts_code

_tickflow: TickFlow | None = None


class KlineSource(Protocol):
    """Interface for daily K-line fetch behind the TickFlow seam."""

    def fetch_daily(self, code: str, start: str, end: str) -> pd.DataFrame: ...


def get_tickflow_client() -> TickFlow:
    global _tickflow
    if _tickflow is None:
        _tickflow = TickFlow.free()
    return _tickflow


def convert_tickflow_df(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    if "trade_date" in df.columns:
        out = pd.DataFrame({"date": pd.to_datetime(df["trade_date"], errors="coerce")})
    elif "timestamp" in df.columns:
        out = pd.DataFrame({"date": pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")})
    else:
        return pd.DataFrame()

    for col in ["open", "high", "low", "close", "volume", "amount"]:
        out[col] = pd.to_numeric(df[col], errors="coerce")

    out = out.sort_values("date").reset_index(drop=True)
    out["pct_chg"] = out["close"].pct_change() * 100

    start_dt = pd.to_datetime(normalize_market_date(start), format="%Y%m%d")
    end_dt = pd.to_datetime(normalize_market_date(end), format="%Y%m%d")
    out = out[(out["date"] >= start_dt) & (out["date"] <= end_dt)]

    out = out[COLUMNS].copy()
    out["volume"] = out["volume"].fillna(0).astype(int)
    out["amount"] = out["amount"].fillna(0).round(2)
    for col in ["open", "high", "low", "close", "pct_chg"]:
        out[col] = out[col].round(2)

    return out.sort_values("date").reset_index(drop=True)


class TickFlowAdapter:
    """Production K-line source backed by TickFlow."""

    def __init__(self, client: TickFlow | None = None) -> None:
        self._client = client

    @property
    def client(self) -> TickFlow:
        return self._client or get_tickflow_client()

    def fetch_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        random_sleep_50_to_150ms()
        ts_code = code2ts_code(code)
        try:
            df = self.client.klines.get(
                ts_code,
                period="1d",
                start_time=date_to_ms(normalize_market_date(start)),
                end_time=date_to_ms(normalize_market_date(end), end_of_day=True),
                adjust="forward",
                as_dataframe=True,
            )
        except Exception as e:
            if looks_like_ip_ban(e):
                raise RateLimitError(str(e)) from e
            raise

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return pd.DataFrame()

        return convert_tickflow_df(df, start, end)


_default_adapter: TickFlowAdapter | None = None


def get_adapter() -> TickFlowAdapter:
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = TickFlowAdapter()
    return _default_adapter
