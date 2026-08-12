from __future__ import annotations

import argparse
import sys

from stock_radar.core.logger import get_logger
from stock_radar.core.time import date_to_ms, market_now
from stock_radar.market.fetch_data import _normalize_date, get_tickflow_client, is_trade_date
from stock_radar.market.load_stocklist import code2ts_code

_BENCHMARK = "600000"
logger = get_logger("fetch")


def _log_tickflow_response(target: str) -> None:
    """Log raw TickFlow response to help distinguish API errors from non-trading days."""
    try:
        raw = get_tickflow_client().klines.get(
            code2ts_code(_BENCHMARK),
            period="1d",
            start_time=date_to_ms(target),
            end_time=date_to_ms(target, end_of_day=True),
            adjust="forward",
            as_dataframe=True,
        )
        if raw is None or raw.empty:
            logger.info("TickFlow 响应: 空")
            return
        trade_dates = raw["trade_date"].tolist() if "trade_date" in raw.columns else []
        logger.info("TickFlow 响应: rows=%d trade_dates=%s", len(raw), trade_dates)
    except Exception as e:
        logger.warning("TickFlow 请求异常: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 TickFlow 日线判断是否为 A 股交易日（有 K 线数据即交易日）"
    )
    parser.add_argument("--date", default="today", help="YYYY-MM-DD / YYYYMMDD / today")
    parser.add_argument("-q", "--quiet", action="store_true", help="仅通过退出码表示结果")
    args = parser.parse_args()

    target = _normalize_date(args.date)
    if not args.quiet:
        logger.info("市场时间(Asia/Shanghai): %s", market_now().isoformat())
        logger.info("查询日期: %s", target)

    traded = is_trade_date(target)

    if not args.quiet:
        if not traded:
            _log_tickflow_response(target)
        if traded:
            logger.info("%s 是交易日", target)
        else:
            logger.info("%s 非交易日", target)

    sys.exit(0 if traded else 1)


if __name__ == "__main__":
    main()
