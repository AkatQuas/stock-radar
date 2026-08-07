from __future__ import annotations

import argparse
from pathlib import Path

from stock_radar.core.logger import get_logger
from stock_radar.core.time import get_today_name
from stock_radar.market.data_utils import load_data_folder
from stock_radar.market.load_stocklist import load_total_stocklist
from stock_radar.notify.lark_notify import send_report_as_doc
from stock_radar.notify.lark_report import build_risk_report_md
from stock_radar.strategy.loader import load_risk_selectors

logger = get_logger("risk")


def main():
    p = argparse.ArgumentParser(
        description="Run risk selectors from risk.config.json over CSV K-line data"
    )
    p.add_argument("--data-dir", type=Path, required=True, help="行情数据目录， CSV K线数据")
    p.add_argument("--date", help="交易日 YYYY-MM-DD，默认=数据最新日期")
    p.add_argument("--send-lark", action="store_true", help="发送Lark通知")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error("数据目录 %s 不存在", data_dir)
        return

    try:
        data, trade_date = load_data_folder(data_dir, date=args.date)
    except Exception as e:
        logger.error("加载行情失败: %s", e)
        return

    logger.info("Detecting risks for %s (%s)", trade_date.date(), trade_date.day_name())

    stocklist = load_total_stocklist()
    selectors = load_risk_selectors()

    per_selector_hits: dict[str, list[str]] = {}
    aggregated: dict[str, list[str]] = {}

    for name, sel in selectors.items():
        try:
            hits = sel.select(trade_date, data)
        except Exception:
            logger.exception("selector %s raised", name)
            hits = []
        per_selector_hits[name] = hits
        for code in hits:
            aggregated.setdefault(code, []).append(name)

    if aggregated:
        header = f"===Aggregated risk summary ({len(aggregated)} symbols) ==="
        out_lines: list[str] = [header]
        for code, reasons in sorted(aggregated.items(), key=lambda kv: len(kv[1]), reverse=True):
            info = next((s for s in stocklist if s["symbol"] == code), None)
            if info:
                name = info.get("name", "")
                name_padded = name.ljust(5)
                url = info.get("xueqiu_url", "")
                out_lines.append(
                    f"{code}, {name_padded}({url}) => {len(reasons)} flags: {', '.join(reasons)}"
                )
            else:
                out_lines.append(f"{code} => {len(reasons)} flags: {', '.join(reasons)}")

        logger.info("\n%s", "\n".join(out_lines))
    else:
        logger.info("No risky symbols detected by selectors.")

    if args.send_lark:
        title = f"{trade_date.date()}[{trade_date.day_name()}]风险检测"
        markdown = build_risk_report_md(aggregated, stocklist)
        summary = f"风险检测 — {trade_date.date()} {trade_date.day_name()}"
        if send_report_as_doc(title=title, markdown=markdown, summary=summary):
            logger.info("已发送风险检测报告文档链接到 Lark")
        else:
            logger.error("发送 Lark 通知失败")

    logger.info("Done. %s", get_today_name())


if __name__ == "__main__":
    main()
