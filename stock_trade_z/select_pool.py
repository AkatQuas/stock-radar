from __future__ import annotations

import argparse
from pathlib import Path

from stock_trade_z.core.logger import get_logger
from stock_trade_z.llm.llm_analyze import analyze_picks
from stock_trade_z.llm.llm_context import build_pick_records
from stock_trade_z.market.data_utils import load_data_folder
from stock_trade_z.market.load_stocklist import load_total_stocklist
from stock_trade_z.market.trend_context import TrendContext, load_trend_context
from stock_trade_z.notify.lark_notify import send_report_as_doc
from stock_trade_z.notify.lark_report import build_pool_select_report_md
from stock_trade_z.strategy.loader import load_pool_selectors

logger = get_logger("select")


def _pool_tags(ctx: TrendContext, symbol: str) -> str:
    meta = ctx.meta_for(symbol)
    if not meta:
        return ""
    parts: list[str] = []
    pool = meta.get("pool")
    if pool:
        parts.append(str(pool))
    if meta.get("lbc") is not None:
        parts.append(f"连板{meta['lbc']}")
    if meta.get("fbt"):
        parts.append(f"封{meta['fbt']}")
    return " ".join(parts)


def main() -> None:
    p = argparse.ArgumentParser(description="运行 pool_selector.config.json 股池战法")
    p.add_argument("--data-dir", type=Path, required=True, help="股池 K 线目录 data-pool/")
    p.add_argument("--trend-dir", type=Path, required=True, help="股池快照目录 trend/")
    p.add_argument("--date", help="交易日 YYYY-MM-DD，默认=数据最新日期")
    p.add_argument("--send-lark", action="store_true", help="发送 Lark 通知")
    p.add_argument(
        "--llm-analyze", action="store_true", help="DeepSeek 排序复盘（需 DEEPSEEK_API_KEY）"
    )
    p.add_argument("--llm-max", type=int, default=50, help="送入 LLM 的最大标的数")
    args = p.parse_args()

    if not args.data_dir.exists():
        logger.error("data-dir 不存在: %s", args.data_dir)
        return

    if not args.trend_dir.exists():
        logger.error("trend-dir 不存在: %s", args.trend_dir)
        return

    try:
        data, trade_date = load_data_folder(args.data_dir, date=args.date)
    except Exception as e:
        logger.error("加载股池 K 线失败: %s", e)
        return

    try:
        trend_ctx = load_trend_context(args.trend_dir, args.date or trade_date.strftime("%Y-%m-%d"))
    except Exception as e:
        logger.error("加载股池快照失败: %s", e)
        return

    pools = trend_ctx.pools
    selector_dict = load_pool_selectors()
    stocklist = load_total_stocklist()
    stock_by_sym = {s["symbol"]: s for s in stocklist}

    logger.info(
        "股池选股开始 | %s %s | qsgc=%d ztgc=%d\n",
        trade_date.date(),
        trade_date.day_name(),
        len(pools.get("qsgc", [])),
        len(pools.get("ztgc", [])),
    )

    all_results: list[dict] = []
    for alias, selector in selector_dict.items():
        picks = selector.select(trade_date, data, pools)
        if not picks:
            logger.info("===[%s] 无结果===\n", alias)
            continue

        logger.info("===[%s] 股池结果 (%d)===", alias, len(picks))
        stocks = []
        for sym in picks:
            info = stock_by_sym.get(sym, {"symbol": sym, "name": sym, "xueqiu_url": ""})
            stocks.append(
                {
                    "symbol": sym,
                    "name": info.get("name", sym),
                    "url": info.get("xueqiu_url", ""),
                    "tags": _pool_tags(trend_ctx, sym),
                }
            )
            logger.info("%s %s %s", sym, info.get("name", ""), _pool_tags(trend_ctx, sym))

        all_results.append({"selector": alias, "count": len(picks), "stocks": stocks})

    llm_section = None
    if args.llm_analyze and all_results:
        market_context = {
            "qsgc_count": len(pools.get("qsgc", [])),
            "ztgc_count": len(pools.get("ztgc", [])),
        }
        records = build_pick_records(
            track="pool",
            trade_date=trade_date,
            results=all_results,
            data=data,
            trend_ctx=trend_ctx,
            market_context=market_context,
            max_stocks=args.llm_max,
        )
        llm_section = analyze_picks(records, trade_date, track="pool")

    if args.send_lark:
        title = f"{trade_date.date()}[{trade_date.day_name()}]股池选股"
        markdown = build_pool_select_report_md(all_results, llm_section)
        summary = f"强势股/涨停选股 — {trade_date.date()} {trade_date.day_name()}"
        if send_report_as_doc(title=title, markdown=markdown, summary=summary):
            logger.info("已发送股池选股报告文档链接到 Lark")
        else:
            logger.error("发送 Lark 失败")


if __name__ == "__main__":
    main()
