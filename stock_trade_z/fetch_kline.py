from __future__ import annotations

import argparse
import datetime as dt
import warnings
from pathlib import Path

from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.utils import ensure_folder
from stock_trade_z.market.fetch_data import fetch_batch_data
from stock_trade_z.market.load_stocklist import load_stock_from_file

warnings.filterwarnings("ignore")

logger = get_logger("fetch")


def main():
    parser = argparse.ArgumentParser(
        description="从 stocklist 读取股票池并用 TickFlow 批量抓取日线 K 线（前复权）"
    )
    parser.add_argument("--start", default="20250101", help="起始日期 YYYYMMDD 或 'today'")
    parser.add_argument("--end", default="today", help="结束日期 YYYYMMDD 或 'today'")
    parser.add_argument(
        "--stocklist",
        type=Path,
        help="股票清单CSV路径（需含 ts_code 或 symbol）",
    )
    parser.add_argument(
        "--exclude-boards",
        nargs="*",
        default=["star", "bj"],
        choices=["gem", "star", "bj"],
        help="排除板块，可多选：gem(创业板300/301) star(科创板688) bj(北交所.BJ/4/8)",
    )
    parser.add_argument("--out", default=Path("./data"), help="输出目录")
    args = parser.parse_args()

    exclude_boards = set(args.exclude_boards or [])
    stock_list = load_stock_from_file(args.stocklist, exclude_boards)

    if len(stock_list) == 0:
        logger.warning("stocklist 为空或被过滤后无代码，请检查。")
        return

    start = dt.date.today().strftime("%Y%m%d") if str(args.start).lower() == "today" else args.start
    end = dt.date.today().strftime("%Y%m%d") if str(args.end).lower() == "today" else args.end
    out_dir = ensure_folder(args.out)
    codes = [s["symbol"] for s in stock_list]

    logger.info(
        "开始抓取 %d 支股票 | 数据源:TickFlow(日线,前复权) | 日期:%s → %s | 排除:%s",
        len(codes),
        start,
        end,
        ",".join(sorted(exclude_boards)) or "无",
    )

    batch = fetch_batch_data(codes, start, end)
    ok, fail = 0, 0
    for code, df in batch.items():
        if df is None:
            fail += 1
            logger.error("%s 抓取失败，已跳过", code)
            continue
        df.to_csv(out_dir / f"{code}.csv", index=False)
        ok += 1

    logger.info("全部任务完成: 成功 %d, 失败 %d → %s", ok, fail, out_dir.resolve())
    if ok == 0:
        logger.warning("所有任务均失败，很遗憾。")
        return


if __name__ == "__main__":
    main()
