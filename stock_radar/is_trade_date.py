from __future__ import annotations

import argparse
import sys

from stock_radar.core.logger import get_logger
from stock_radar.core.time import market_now, normalize_market_date
from stock_radar.market.calendar import TRADE_DATE_BENCHMARK, fetch_benchmark_daily, is_trade_date

logger = get_logger("fetch")


def _log_tickflow_response(target: str) -> None:
    """Log raw benchmark response to help distinguish API errors from non-trading days."""
    try:
        raw = fetch_benchmark_daily(target, benchmark=TRADE_DATE_BENCHMARK)
        if raw is None or raw.empty:
            logger.info("TickFlow 响应: 空")
            return
        trade_dates = raw["date"].dt.strftime("%Y%m%d").tolist()
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

    target = normalize_market_date(args.date)
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
