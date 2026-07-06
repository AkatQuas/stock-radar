from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from stock_trade_z.lib.fetch_data import fetch_batch_data
from stock_trade_z.lib.logger import get_logger
from stock_trade_z.lib.trend_context import pool_symbols_from_dir
from stock_trade_z.lib.utils import ensure_folder

logger = get_logger("fetch")


def main() -> None:
    parser = argparse.ArgumentParser(description="为 qsgc/ztgc 股池标的抓取 TickFlow 日线 K 线")
    parser.add_argument(
        "--trend-dir", type=Path, required=True, help="股池目录 (含 YYYY-MM-DD 子目录)"
    )
    parser.add_argument("--date", help="交易日 YYYY-MM-DD，默认 trend-dir 下最新日期")
    parser.add_argument("--start", default="20240101", help="K线起始 YYYYMMDD 或 today")
    parser.add_argument("--end", default="today", help="K线结束 YYYYMMDD 或 today")
    parser.add_argument("--out", type=Path, default=Path("./data-pool"), help="输出目录")
    args = parser.parse_args()

    if not args.trend_dir.exists():
        logger.warning("trend-dir 不存在: %s", args.trend_dir)
        return

    try:
        symbols = pool_symbols_from_dir(args.trend_dir, args.date)
    except FileNotFoundError as e:
        logger.error("从目录获取股池失败 %s", e)
        return

    if not symbols:
        logger.warning("股池为空，跳过 K 线抓取")
        return

    start = dt.date.today().strftime("%Y%m%d") if str(args.start).lower() == "today" else args.start
    end = dt.date.today().strftime("%Y%m%d") if str(args.end).lower() == "today" else args.end
    out_dir = ensure_folder(args.out)

    logger.info(
        "TickFlow 股池 K 线 | %d 支 | %s → %s | 输出:%s",
        len(symbols),
        start,
        end,
        out_dir,
    )

    batch = fetch_batch_data(symbols, start, end)
    ok = 0
    for code, df in batch.items():
        if df is None:
            logger.error("%s 抓取失败，已跳过", code)
            continue
        df.to_csv(out_dir / f"{code}.csv", index=False)
        ok += 1

    logger.info("股池 K 线完成: %d/%d 保存至 %s", ok, len(symbols), out_dir.resolve())


if __name__ == "__main__":
    main()
