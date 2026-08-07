import argparse
from typing import Any

import pandas as pd

from stock_radar.core.logger import get_logger
from stock_radar.market.bao_stock_client import BSClient
from stock_radar.market.load_stocklist import StockCodeDict, load_total_stocklist
from stock_radar.strategy.loader import load_selectors

logger = get_logger("check")


def check_symbol(
    symbol: str,
    total: list[StockCodeDict],
    selector_dict: dict[str, Any],
) -> None:
    """检查单个股票代码是否符合战法"""
    matched = next((item for item in total if item.get("symbol") == symbol), None)
    if matched is None:
        logger.error("全量 stocklist 中没有找到 %s\n", symbol)
        return

    logger.info("对 %s_%s 进行检测 \n\n", matched["symbol"], matched["name"])
    df: None | pd.DataFrame = None
    with BSClient() as bs:
        df = bs.fetch_one_data(matched["symbol"], "2023-01-01")

    if df is None:
        logger.error("无法获取到日 K\n")
        return

    # 提示数据异常
    if df["date"].isna().any():
        logger.error("date 列存在异常，无法处理\n")
        return

    # df.to_csv("./data/00temp_bs.csv", index= False)
    trade_date = df["date"].max()
    logger.info(
        "检查 %s(%s) %s, 交易日: %s %s 。 \n\n",
        matched["symbol"],
        matched["name"],
        matched["xueqiu_url"],
        trade_date.date(),
        trade_date.day_name(),
    )
    match_selector = []
    # --- 逐个 Selector 运行 ---
    for alias, selector in selector_dict.items():
        picks = selector.select(trade_date, {f"{matched['symbol']}": df})

        # 将结果写入日志，同时输出到控制台
        if len(picks) > 0:
            match_selector.append(alias)

    if len(match_selector) > 0:
        logger.info("===符合战法===\n %s\n\n", ", ".join(match_selector))
    else:
        logger.info("===无匹配 战法===\n\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="对给定的证券编码，用 Tushare 抓取日线K线（固定qfq，全量覆盖），后再判断它是否符合某一战法"
    )
    # 抓取范围
    parser.add_argument(
        "--symbol", type=str, help="股票证券代码 6 位（可选，不提供则进入交互模式）"
    )

    args = parser.parse_args()
    total = load_total_stocklist()
    selector_dict = load_selectors()

    # 单次运行模式
    if args.symbol:
        check_symbol(args.symbol, total, selector_dict)
        return

    # 交互模式
    logger.info("进入交互模式，输入股票代码进行检测（输入 'quit' 或 'exit' 退出）\n")
    while True:
        try:
            symbol = input("\n请输入股票代码（6位）: ").strip()
            print("")

            if symbol.lower() in ["quit", "exit", "q"]:
                logger.info("退出交互模式\n")
                break

            if not symbol:
                continue

            if len(symbol) != 6 or not symbol.isdigit():
                logger.warning(" 请输入有效的6位数字股票代码\n")
                continue

            check_symbol(symbol, total, selector_dict)

        except KeyboardInterrupt:
            logger.info("\n检测到中断信号，退出交互模式\n")
            break
        except Exception as e:
            logger.error("处理过程中出错: %s\n", str(e))
            continue


if __name__ == "__main__":
    main()
