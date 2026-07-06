from __future__ import annotations

import argparse
from pathlib import Path

from stock_trade_z.lib.data_utils import load_data_folder
from stock_trade_z.lib.lark_notify import send_report_as_doc
from stock_trade_z.lib.lark_report import build_select_report_md
from stock_trade_z.lib.llm_analyze import analyze_picks
from stock_trade_z.lib.llm_context import build_pick_records
from stock_trade_z.lib.load_selector import load_selectors
from stock_trade_z.lib.load_stocklist import load_total_stocklist
from stock_trade_z.lib.logger import get_logger

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

    selector_dict = load_selectors()
    stocklist = load_total_stocklist()

    logger.info(
        "开始本轮选股, 交易日: %s %s 。 \n\n",
        trade_date.date(),
        trade_date.day_name(),
    )

    all_results = []
    for alias, selector in selector_dict.items():
        picks = selector.select(trade_date, data)

        if len(picks) > 0:
            logger.info("===[%s] 选股结果 (%d)===", alias, len(picks))
            filtered_list = [s for s in stocklist if s["symbol"] in picks]
            single_str_list = [
                f"{s['symbol']}, {s['name'].ljust(5)}({s['xueqiu_url']})" for s in filtered_list
            ]
            big_string = "\n".join(single_str_list)
            logger.info("\n\n%s\n\n", big_string)

            all_results.append(
                {
                    "selector": alias,
                    "count": len(picks),
                    "stocks": [
                        {
                            "symbol": s["symbol"],
                            "name": s["name"],
                            "url": s["xueqiu_url"],
                        }
                        for s in filtered_list
                    ],
                }
            )
        else:
            logger.info("===[%s] 无结果===\n\n", alias)

    llm_section = None
    if args.llm_analyze and all_results:
        records = build_pick_records(
            track="normal",
            trade_date=trade_date,
            results=all_results,
            data=data,
            max_stocks=args.llm_max,
        )
        llm_section = analyze_picks(records, trade_date, track="normal")

    if args.send_lark:
        title = f"{trade_date.date()}[{trade_date.day_name()}]选股结果"
        markdown = build_select_report_md(all_results, llm_section)
        summary = f"选股结果 — {trade_date.date()} {trade_date.day_name()}"
        if send_report_as_doc(title=title, markdown=markdown, summary=summary):
            logger.info("已发送选股报告文档链接到 Lark")
        else:
            logger.error("发送 Lark 通知失败")


if __name__ == "__main__":
    main()
