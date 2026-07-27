"""TickFlow K-line fetcher (active implementation)."""

from __future__ import annotations

import random
import re
import time

import pandas as pd
from tickflow import TickFlow

from stock_trade_z.core.constant import COLUMNS, RateLimitError
from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.time import date_to_ms, get_today_date, validate
from stock_trade_z.core.utils import looks_like_ip_ban, random_sleep_50_to_150ms, sleep_progress
from stock_trade_z.market.load_stocklist import StockCodeDict, code2ts_code

BATCH_SIZE = 12
BATCH_GAP_SECONDS = 65
MAX_RETRIES = 3
# Liquid A-share used to probe whether the market traded on a given day.
_TRADE_DATE_BENCHMARK = "600000"

_tickflow: TickFlow | None = None


def get_tickflow_client() -> TickFlow:
    global _tickflow
    if _tickflow is None:
        _tickflow = TickFlow.free()
    return _tickflow


def _normalize_date(date: str) -> str:
    if str(date).lower() == "today":
        return get_today_date()
    text = str(date).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text.replace("-", "")
    return text


def is_trade_date(date: str | None = None, *, benchmark: str = _TRADE_DATE_BENCHMARK) -> bool:
    """Return True when TickFlow has a daily bar for `date` (A-share trading day)."""
    target = _normalize_date(date or "today")
    df = _get_kline_tickflow(benchmark, target, target)
    if df is None or df.empty:
        return False
    target_day = pd.to_datetime(target, format="%Y%m%d").normalize()
    return bool((df["date"].dt.normalize() == target_day).any())


def _convert_tickflow_df(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
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

    start_dt = pd.to_datetime(_normalize_date(start), format="%Y%m%d")
    end_dt = pd.to_datetime(_normalize_date(end), format="%Y%m%d")
    out = out[(out["date"] >= start_dt) & (out["date"] <= end_dt)]

    out = out[COLUMNS].copy()
    out["volume"] = out["volume"].fillna(0).astype(int)
    out["amount"] = out["amount"].fillna(0).round(2)
    for col in ["open", "high", "low", "close", "pct_chg"]:
        out[col] = out[col].round(2)

    return out.sort_values("date").reset_index(drop=True)


def _get_kline_tickflow(code: str, start: str, end: str) -> pd.DataFrame:
    random_sleep_50_to_150ms()
    ts_code = code2ts_code(code)
    tf = get_tickflow_client()
    try:
        df = tf.klines.get(
            ts_code,
            period="1d",
            start_time=date_to_ms(_normalize_date(start)),
            end_time=date_to_ms(_normalize_date(end), end_of_day=True),
            adjust="forward",
            as_dataframe=True,
        )
    except Exception as e:
        if looks_like_ip_ban(e):
            raise RateLimitError(str(e)) from e
        raise

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame()

    return _convert_tickflow_df(df, start, end)


def fetch_batch_data(
    codes: list[str],
    start: str,
    end: str,
) -> dict[str, pd.DataFrame | None]:
    """Batch fetch k-lines via TickFlow (BATCH_SIZE per request, BATCH_GAP_SECONDS between)."""
    logger = get_logger("fetch")
    start = _normalize_date(start)
    end = _normalize_date(end)
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
                start_time=date_to_ms(_normalize_date(start)),
                end_time=date_to_ms(_normalize_date(end), end_of_day=True),
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
                    results[code] = validate(_convert_tickflow_df(df, start, end))
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
    start = _normalize_date(start)
    end = _normalize_date(end)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            new_df = _get_kline_tickflow(code, start, end)
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
