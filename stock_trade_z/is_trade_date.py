from __future__ import annotations

import argparse
import sys

from stock_trade_z.core.logger import get_logger
from stock_trade_z.market.fetch_data import _normalize_date, is_trade_date

logger = get_logger("fetch")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 TickFlow 日线判断是否为 A 股交易日（有 K 线数据即交易日）"
    )
    parser.add_argument("--date", default="today", help="YYYY-MM-DD / YYYYMMDD / today")
    parser.add_argument("-q", "--quiet", action="store_true", help="仅通过退出码表示结果")
    args = parser.parse_args()

    target = _normalize_date(args.date)
    traded = is_trade_date(target)

    if not args.quiet:
        if traded:
            logger.info("%s 是交易日", target)
        else:
            logger.info("%s 非交易日", target)

    sys.exit(0 if traded else 1)


if __name__ == "__main__":
    main()
