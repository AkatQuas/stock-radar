"""Zhitu trend pool snapshots (qsgc / ztgc metadata only)."""

from __future__ import annotations

import re

import pandas as pd
import requests

from stock_radar.core.constant import RateLimitError
from stock_radar.core.logger import get_logger
from stock_radar.core.utils import looks_like_ip_ban, random_sleep_50_to_150ms
from stock_radar.market.rate_limit import SlidingWindowRateLimiter
from stock_radar.market.zhitu_api import get_zhitu_token

POOL_URL = "https://api.zhituapi.com/hs/pool/{pool}/{trade_date}"
POOL_NAMES = ("qsgc", "ztgc")
REQUEST_TIMEOUT = 30

_pool_rate_limiter = SlidingWindowRateLimiter(max_calls=50, period_seconds=60.0)


def _normalize_trade_date(trade_date: str) -> str:
    """Accept YYYY-MM-DD or YYYYMMDD."""
    trade_date = str(trade_date).strip()
    if trade_date.lower() == "today":
        from stock_radar.core.time import get_today_date

        return pd.to_datetime(get_today_date(), format="%Y%m%d").strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{8}", trade_date):
        return pd.to_datetime(trade_date, format="%Y%m%d").strftime("%Y-%m-%d")
    return trade_date


def _parse_yes_flag(value) -> int:
    """Parse 是/否 or numeric flags to 0/1."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    if isinstance(value, (int, float)) and not pd.isna(value):
        return 1 if int(value) != 0 else 0
    text = str(value).strip()
    if not text:
        return 0
    if text in ("是", "yes", "Y", "y", "true", "True", "TRUE"):
        return 1
    if text in ("否", "no", "N", "n", "false", "False", "FALSE"):
        return 0
    try:
        return 1 if int(float(text)) != 0 else 0
    except ValueError:
        return 0


def _parse_tj(tj: str) -> tuple[int | None, int | None]:
    if not tj or not isinstance(tj, str):
        return None, None
    m = re.match(r"(\d+)天/(\d+)板", tj.strip())
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _normalize_pool_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "dm" in out.columns:
        out["symbol"] = out["dm"].astype(str).str.zfill(6)
    elif "symbol" not in out.columns:
        return pd.DataFrame()

    if "mc" in out.columns:
        out["name"] = out["mc"].astype(str)

    if "tj" in out.columns:
        parsed = out["tj"].apply(_parse_tj)
        out["tj_days"] = parsed.apply(lambda x: x[0])
        out["tj_boards"] = parsed.apply(lambda x: x[1])

    if "nh" in out.columns:
        out["nh"] = out["nh"].apply(_parse_yes_flag)

    return out


def fetch_pool(trade_date: str, pool_name: str) -> pd.DataFrame:
    """Fetch one Zhitu pool snapshot for a trade date."""
    if pool_name not in POOL_NAMES:
        raise ValueError(f"unsupported pool: {pool_name}")

    random_sleep_50_to_150ms()
    _pool_rate_limiter.acquire()

    date_str = _normalize_trade_date(trade_date)
    url = POOL_URL.format(pool=pool_name, trade_date=date_str)
    params = {"token": get_zhitu_token()}

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
        raise RuntimeError(f"智图股池 API 返回错误: {msg}")

    if not isinstance(payload, list) or len(payload) == 0:
        return pd.DataFrame()

    return _normalize_pool_df(pd.DataFrame(payload))


def fetch_pools(
    trade_date: str, pool_names: tuple[str, ...] = POOL_NAMES
) -> dict[str, pd.DataFrame]:
    logger = get_logger("fetch")
    results: dict[str, pd.DataFrame] = {}
    for name in pool_names:
        try:
            df = fetch_pool(trade_date, name)
            results[name] = df
            logger.info("%s %s: %d 条", trade_date, name, len(df))
        except Exception as e:
            logger.error("%s 抓取失败: %s", name, e)
            results[name] = pd.DataFrame()
    return results
