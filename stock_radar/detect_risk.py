from __future__ import annotations

import argparse
from pathlib import Path

from stock_radar.core.logger import get_logger
from stock_radar.core.time import get_today_name
from stock_radar.market.data_utils import load_data_folder
from stock_radar.market.load_stocklist import load_total_stocklist
from stock_radar.strategy.loader import load_risk_selectors
from stock_radar.strategy.run_risk import RiskOptions, run_risk_detection

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

    run_risk_detection(
        selectors=load_risk_selectors(),
        data=data,
        trade_date=trade_date,
        stocklist=load_total_stocklist(),
        opts=RiskOptions(send_lark=args.send_lark),
        report_title=f"{trade_date.date()}[{trade_date.day_name()}]风险检测",
        report_summary=f"风险检测 — {trade_date.date()} {trade_date.day_name()}",
    )

    logger.info("Done. %s", get_today_name())


if __name__ == "__main__":
    main()
