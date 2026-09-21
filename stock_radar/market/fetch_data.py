"""TickFlow K-line fetcher (active implementation)."""

from __future__ import annotations

import random
import time

import pandas as pd

from stock_radar.core.constant import COLUMNS, RateLimitError
from stock_radar.core.logger import get_logger
from stock_radar.core.time import date_to_ms, normalize_market_date, validate
from stock_radar.core.utils import random_sleep_50_to_150ms, sleep_progress
from stock_radar.market.calendar import is_trade_date
from stock_radar.market.load_stocklist import StockCodeDict, code2ts_code
from stock_radar.market.tickflow_adapter import (
    convert_tickflow_df,
    get_adapter,
    get_tickflow_client,
)

BATCH_SIZE = 12
BATCH_GAP_SECONDS = 65
MAX_RETRIES = 3

__all__ = [
    "BATCH_GAP_SECONDS",
    "BATCH_SIZE",
    "MAX_RETRIES",
    "fetch_batch_data",
    "fetch_many_data",
    "fetch_one_data",
    "get_tickflow_client",
    "is_trade_date",
]


def fetch_batch_data(
    codes: list[str],
    start: str,
    end: str,
) -> dict[str, pd.DataFrame | None]:
    """Batch fetch k-lines via TickFlow (BATCH_SIZE per request, BATCH_GAP_SECONDS between)."""
    logger = get_logger("fetch")
    start = normalize_market_date(start)
    end = normalize_market_date(end)
    tf = get_tickflow_client()
    results: dict[str, pd.DataFrame | None] = {}

    symbols = [code2ts_code(code) for code in codes]
    chunks = [symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    code_by_symbol = {code2ts_code(code): code for code in codes}

    for idx, chunk in enumerate(chunks):
        task_idx = idx + 1
        logger.info(
            "TickFlow batch %d/%d，%d 支股票",
            task_idx,
            len(chunks),
            len(chunk),
        )
        random_sleep_50_to_150ms()
        try:
            batch_data = tf.klines.batch(
                chunk,
                period="1d",
                start_time=date_to_ms(normalize_market_date(start)),
                end_time=date_to_ms(normalize_market_date(end), end_of_day=True),
                adjust="forward",
                as_dataframe=True,
                show_progress=False,
            )
        except Exception as e:
            logger.error("TickFlow batch %d 失败: %s", task_idx, e)
            for symbol in chunk:
                results[code_by_symbol[symbol]] = None
            if task_idx < len(chunks):
                sleep_progress(BATCH_GAP_SECONDS, desc="TickFlow batch throttle")
            continue

        for symbol in chunk:
            code = code_by_symbol[symbol]
            try:
                df = batch_data.get(symbol)
                if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                    results[code] = pd.DataFrame(columns=COLUMNS)
                else:
                    results[code] = validate(convert_tickflow_df(df, start, end))
            except Exception as e:
                logger.error("%s TickFlow 转换失败: %s", code, e)
                results[code] = None

        if task_idx < len(chunks):
            sleep_progress(BATCH_GAP_SECONDS, desc="TickFlow batch throttle")

    return results


def fetch_many_data(
    stocks: list[StockCodeDict],
    start: str,
    end: str,
) -> dict[str, pd.DataFrame | None]:
    codes = [stock["symbol"] for stock in stocks]
    return fetch_batch_data(codes, start, end)


def fetch_one_data(
    code: str,
    start: str,
    end: str,
) -> pd.DataFrame | None:
    """Fetch one symbol via TickFlow with retries."""
    logger = get_logger("fetch")
    start = normalize_market_date(start)
    end = normalize_market_date(end)
    adapter = get_adapter()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            new_df = adapter.fetch_daily(code, start, end)
            if new_df.empty:
                logger.debug("%s TickFlow 无数据，生成空表。", code)
                new_df = pd.DataFrame(columns=COLUMNS)
            return validate(new_df)
        except RateLimitError as e:
            wait = random.uniform(BATCH_GAP_SECONDS * 0.9, BATCH_GAP_SECONDS * 1.1)
            logger.warning(
                "%s TickFlow 第 %d 次命中限流: %s，%.1f 秒后重试",
                code,
                attempt,
                e,
                wait,
            )
            time.sleep(wait)
        except Exception as e:
            wait = random.uniform(2.0, 6.0) * attempt
            logger.info(
                "%s TickFlow 第 %d 次抓取失败: %s，%.1f 秒后重试",
                code,
                attempt,
                e,
                wait,
            )
            time.sleep(wait)
    else:
        logger.error("%s TickFlow 抓取失败，已跳过（不影响其他任务）", code)
        return None
