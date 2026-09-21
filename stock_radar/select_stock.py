from __future__ import annotations

import argparse
from pathlib import Path

from stock_radar.core.logger import get_logger
from stock_radar.market.data_utils import load_data_folder
from stock_radar.market.load_stocklist import load_total_stocklist
from stock_radar.notify.lark_report import build_select_report_md
from stock_radar.strategy.loader import load_selectors
from stock_radar.strategy.run_selection import SelectionOptions, run_selection

logger = get_logger("select")


def main():
    p = argparse.ArgumentParser(description="Run selectors defined in selector.config.json")
    p.add_argument("--data-dir", type=Path, required=True, help="行情数据目录， CSV K线数据")
    p.add_argument("--date", help="交易日 YYYY-MM-DD ，默认=数据最新日期")
    p.add_argument("--send-lark", action="store_true", help="发送Lark通知")
    p.add_argument(
        "--llm-analyze", action="store_true", help="DeepSeek 排序复盘（需 DEEPSEEK_API_KEY）"
    )
    p.add_argument("--llm-max", type=int, default=20, help="送入 LLM 的最大标的数")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error("数据目录 %s 不存在", data_dir)
        return

    try:
        data, trade_date = load_data_folder(data_dir, date=args.date)
    except Exception as e:
        logger.error("加载行情失败，不再继续: %s", e)
        return

    logger.info(
        "开始本轮选股, 交易日: %s %s 。 \n\n",
        trade_date.date(),
        trade_date.day_name(),
    )

    run_selection(
        selectors=load_selectors(),
        data=data,
        trade_date=trade_date,
        stocklist=load_total_stocklist(),
        opts=SelectionOptions(
            llm_analyze=args.llm_analyze,
            llm_max=args.llm_max,
            send_lark=args.send_lark,
            track="normal",
        ),
        report_title=f"{trade_date.date()}[{trade_date.day_name()}]选股结果",
        report_summary=f"选股结果 — {trade_date.date()} {trade_date.day_name()}",
        build_report_md=build_select_report_md,
    )


if __name__ == "__main__":
    main()
