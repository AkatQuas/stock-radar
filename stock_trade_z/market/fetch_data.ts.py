import time

import pandas as pd
import tushare as ts

from stock_trade_z.core.constant import COLUMNS, RateLimitError
from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.time import validate
from stock_trade_z.core.utils import cool_sleep, looks_like_ip_ban
from stock_trade_z.market.load_stocklist import code2ts_code
from stock_trade_z.market.ts_pro_api import get_pro_api


def _get_kline_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    """
    下载股票数据

    参数:
        code: 股票代码 (如: 600000, 000001)
        start: 开始日期 (YYYYMMDD)
        end: 结束日期 (YYYYMMDD)

    返回:
        DataFrame: 股票数据，失败返回None
    """
    ts_pro = get_pro_api()
    ts_code = code2ts_code(code)
    try:
        df: pd.DataFrame | None = ts.pro_bar(
            ts_code=ts_code,
            adj="qfq",
            start_date=start,
            end_date=end,
            freq="D",
            api=ts_pro,
            # factors=["tor"]
        )
    except Exception as e:
        if looks_like_ip_ban(e):
            raise RateLimitError(str(e)) from e
        raise

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"trade_date": "date", "vol": "volume"})[COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["open", "high", "low", "close", "pct_chg"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # 成交量：整数（手），先填充 NaN 为 0 再转换
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    # 成交额：保留2位小数（元），NaN 填充为 0
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).round(2)
    return df.sort_values("date").reset_index(drop=True)


def fetch_one_data(
    code: str,
    start: str,
    end: str,
) -> pd.DataFrame | None:
    """
    fetch data for stock `code`

    .. deprecated::
    """
    logger = get_logger("fetch")
    for attempt in range(1, 4):
        try:
            new_df = _get_kline_tushare(code, start, end)
            if new_df.empty:
                logger.debug("%s 无数据，生成空表。", code)
                new_df = pd.DataFrame(columns=COLUMNS)
            return validate(new_df)
        except Exception as e:
            if looks_like_ip_ban(e):
                logger.error(f"{code} 第 {attempt} 次抓取疑似被封禁，沉睡")
                cool_sleep()
            else:
                silent_seconds = 15 * attempt
                logger.info(f"{code} 第 {attempt} 次抓取失败: {e}. \n{silent_seconds} 秒后重试")
                time.sleep(silent_seconds)
    else:
        return None
