from __future__ import annotations

import argparse
from pathlib import Path

from stock_radar.core.logger import get_logger
from stock_radar.market.data_utils import load_data_folder
from stock_radar.market.load_stocklist import load_total_stocklist
from stock_radar.market.trend_context import TrendContext, load_trend_context
from stock_radar.notify.lark_report import build_pool_select_report_md
from stock_radar.strategy.loader import load_pool_selectors
from stock_radar.strategy.run_selection import SelectionOptions, run_selection

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
    logger.info(
        "股池选股开始 | %s %s | qsgc=%d ztgc=%d\n",
        trade_date.date(),
        trade_date.day_name(),
        len(pools.get("qsgc", [])),
        len(pools.get("ztgc", [])),
    )

    run_selection(
        selectors=load_pool_selectors(),
        data=data,
        trade_date=trade_date,
        stocklist=load_total_stocklist(),
        pools=pools,
        trend_ctx=trend_ctx,
        tag_fn=lambda sym: _pool_tags(trend_ctx, sym),
        market_context={
            "qsgc_count": len(pools.get("qsgc", [])),
            "ztgc_count": len(pools.get("ztgc", [])),
        },
        opts=SelectionOptions(
            llm_analyze=args.llm_analyze,
            llm_max=args.llm_max,
            send_lark=args.send_lark,
            track="pool",
        ),
        report_title=f"{trade_date.date()}[{trade_date.day_name()}]股池选股",
        report_summary=f"强势股/涨停选股 — {trade_date.date()} {trade_date.day_name()}",
        build_report_md=build_pool_select_report_md,
    )


if __name__ == "__main__":
    main()
