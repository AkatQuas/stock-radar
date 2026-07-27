from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.utils import ensure_folder
from stock_trade_z.market.fetch_trend import POOL_NAMES, _normalize_trade_date, fetch_pools

logger = get_logger("fetch")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取智图强势股池/涨停股池快照 (qsgc, ztgc)")
    parser.add_argument("--date", default="today", help="交易日 YYYY-MM-DD / YYYYMMDD / today")
    parser.add_argument("--out", type=Path, default=Path("./trend"), help="输出根目录")
    args = parser.parse_args()

    trade_date = (
        dt.date.today().strftime("%Y-%m-%d")
        if str(args.date).lower() == "today"
        else _normalize_trade_date(args.date)
    )
    out_dir = ensure_folder(args.out / trade_date)

    logger.info("抓取智图股池 | 日期:%s | 输出:%s", trade_date, out_dir)

    pools = fetch_pools(trade_date, POOL_NAMES)
    saved = 0
    for name, df in pools.items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("已保存 %s (%d 条)", path.name, len(df))
        saved += 1

    if saved == 0:
        logger.error("未保存任何股池数据")
        return

    logger.info("股池抓取完成: %s", out_dir.resolve())


if __name__ == "__main__":
    main()
