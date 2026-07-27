from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

# A-share market calendar and session times use China standard time.
MARKET_TZ = ZoneInfo("Asia/Shanghai")


def market_now() -> datetime:
    return datetime.now(MARKET_TZ)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    if df["date"].isna().any():
        raise ValueError("存在缺失日期！")
    today = pd.to_datetime(get_today_date(), format="%Y%m%d")
    if (df["date"] > today).any():
        raise ValueError("数据包含未来日期，可能抓取错误！")
    return df


def get_today_date() -> str:
    return market_now().strftime("%Y%m%d")


def get_today_name() -> str:
    t = pd.Timestamp.now(tz=MARKET_TZ)
    current_date = t.date()
    current_weekday = t.day_name()
    return f"【今天】{current_date}({current_weekday})"


def date_to_ms(date: str, *, end_of_day: bool = False) -> int:
    """Convert YYYYMMDD market calendar date to epoch milliseconds (Asia/Shanghai)."""
    dt = datetime.strptime(str(date), "%Y%m%d").replace(tzinfo=MARKET_TZ)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp() * 1000)
