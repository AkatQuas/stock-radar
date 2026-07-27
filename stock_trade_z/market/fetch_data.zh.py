"""Zhitu K-line fetcher — archived (see fetch_data.py for TickFlow)."""

import random
import time

import pandas as pd
import requests

from stock_trade_z.core.constant import COLUMNS, RateLimitError
from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.time import get_today_date, validate
from stock_trade_z.core.utils import looks_like_ip_ban, random_sleep_50_to_150ms
from stock_trade_z.market.load_stocklist import code2ts_code
from stock_trade_z.market.rate_limit import SlidingWindowRateLimiter
from stock_trade_z.market.zhitu_api import get_zhitu_token

ZHITU_HISTORY_URL = "https://api.zhituapi.com/hs/history/{ts_code}/d/f"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

_zhitu_rate_limiter = SlidingWindowRateLimiter(max_calls=50, period_seconds=60.0)


def _normalize_date(date: str) -> str:
    if str(date).lower() == "today":
        return get_today_date()
    return str(date)


def _get_kline_zhitu(code: str, start: str, end: str) -> pd.DataFrame:
    """
    从智图 API 下载日线前复权 K 线。

    参数:
        code: 股票代码 (如: 600000, 000001)
        start: 开始日期 (YYYYMMDD)
        end: 结束日期 (YYYYMMDD)

    返回:
        DataFrame: 股票数据，无数据时返回空表
    """
    random_sleep_50_to_150ms()
    _zhitu_rate_limiter.acquire()

    ts_code = code2ts_code(code)
    url = ZHITU_HISTORY_URL.format(ts_code=ts_code)
    params = {
        "token": get_zhitu_token(),
        "st": _normalize_date(start),
        "et": _normalize_date(end),
    }

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as e:
        if looks_like_ip_ban(e) or (e.response is not None and e.response.status_code == 429):
            raise RateLimitError(str(e)) from e
        raise
    except Exception as e:
        if looks_like_ip_ban(e):
            raise RateLimitError(str(e)) from e
        raise

    if payload is None:
        return pd.DataFrame()

    if isinstance(payload, dict):
        msg = str(payload.get("msg") or payload.get("message") or payload)
        if looks_like_ip_ban(Exception(msg)):
            raise RateLimitError(msg)
        raise RuntimeError(f"智图 API 返回错误: {msg}")

    if not isinstance(payload, list) or len(payload) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(payload)
    rename_map = {
        "t": "date",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
        "a": "amount",
        "pc": "pc",
    }
    df = df.rename(columns=rename_map)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "amount", "pc"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    pc = df["pc"]
    close = df["close"]
    df["pct_chg"] = ((close - pc) / pc * 100).where(pc > 0)

    df = df[COLUMNS].copy()
    df["volume"] = df["volume"].fillna(0).astype(int)
    df["amount"] = df["amount"].fillna(0).round(2)
    for col in ["open", "high", "low", "close", "pct_chg"]:
        df[col] = df[col].round(2)

    return df.sort_values("date").reset_index(drop=True)


def fetch_one_data(
    code: str,
    start: str,
    end: str,
) -> pd.DataFrame | None:
    """
    fetch data for stock `code`
    """
    logger = get_logger("fetch")
    start = _normalize_date(start)
    end = _normalize_date(end)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            new_df = _get_kline_zhitu(code, start, end)
            if new_df.empty:
                logger.debug("%s 无数据，生成空表。", code)
                new_df = pd.DataFrame(columns=COLUMNS)
            return validate(new_df)
        except RateLimitError as e:
            wait = random.uniform(3.0, 8.0) * attempt
            logger.warning(
                "%s 第 %d 次抓取命中限流: %s，%.1f 秒后重试",
                code,
                attempt,
                e,
                wait,
            )
            time.sleep(wait)
        except Exception as e:
            wait = random.uniform(1.0, 4.0) * attempt
            logger.info(
                "%s 第 %d 次抓取失败: %s，%.1f 秒后重试",
                code,
                attempt,
                e,
                wait,
            )
            time.sleep(wait)
    else:
        logger.error("%s 抓取失败，已跳过（不影响其他任务）", code)
        return None
