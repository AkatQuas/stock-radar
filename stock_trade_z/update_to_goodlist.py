import argparse
from pathlib import Path

import pandas as pd

from stock_trade_z.core.paths import get_file_in_pack
from stock_trade_z.market.load_stocklist import load_stock_from_file_in_df, sort_dataframe


def find_stock_by_symbol(total_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """在总股票列表中查找指定代码的股票。

    Args:
        total_df: 总股票列表 DataFrame
        symbol: 6位股票代码字符串

    Returns:
        匹配的股票记录 DataFrame（可能为空）
    """
    symbol = str(symbol).zfill(6)

    return total_df[total_df["symbol"] == symbol]


def add_stock_to_good(
    total_df: pd.DataFrame, good_df: pd.DataFrame, symbol: str
) -> tuple[pd.DataFrame, bool]:
    """将指定股票添加到好股票列表。

    Args:
        total_df: 总股票列表 DataFrame
        good_df: 现有好股票列表 DataFrame
        symbol: 6位股票代码

    Returns:
        (更新后的 DataFrame, 是否成功添加)
    """
    # 查找股票
    matched = find_stock_by_symbol(total_df, symbol)

    if matched.empty:
        print(f"未找到股票代码: {symbol}")
        return good_df, False

    # 检查是否已存在
    symbol_padded = str(symbol).zfill(6)
    good_df_copy = good_df.copy()
    good_df_copy["symbol"] = good_df_copy["symbol"].astype(str).str.zfill(6)

    if symbol_padded in good_df_copy["symbol"].values:
        stock_name = matched.iloc[0]["name"]
        stock_url = matched.iloc[0]["xueqiu_url"]
        print(f" 股票 {symbol_padded} ({stock_name} {stock_url}) 已存在于列表中")
        return good_df, False

    # 合并数据
    combined_df = pd.concat([good_df, matched], ignore_index=True)

    stock_name = matched.iloc[0]["name"]
    stock_url = matched.iloc[0]["xueqiu_url"]
    print(f"成功添加: {symbol_padded} - {stock_name} ({stock_url})")

    return combined_df, True


def remove_stock_from_good(good_df: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, bool]:
    """从好股票列表中删除指定股票。

    Args:
        good_df: 现有好股票列表 DataFrame
        symbol: 6位股票代码

    Returns:
        (更新后的 DataFrame, 是否成功删除)
    """
    symbol_padded = str(symbol).zfill(6)

    # 标准化 symbol 列进行比较
    good_df_copy = good_df.copy()
    good_df_copy["symbol"] = good_df_copy["symbol"].astype(str).str.zfill(6)

    # 查找股票
    matched_indices = good_df_copy[good_df_copy["symbol"] == symbol_padded].index

    if len(matched_indices) == 0:
        print(f"股票 {symbol_padded} 不在列表中")
        return good_df, False

    # 获取股票名称（用于显示）
    stock_name = good_df.iloc[matched_indices[0]]["name"]
    stock_url = good_df.iloc[matched_indices[0]]["xueqiu_url"]

    # 删除股票
    updated_df = good_df.drop(matched_indices).reset_index(drop=True)

    print(f"🗑️  成功删除: {symbol_padded} - {stock_name} ({stock_url})")

    return updated_df, True


def interactive_mode(
    total_df: pd.DataFrame,
    good_df: pd.DataFrame,
):
    """交互式模式，持续接受用户输入。"""
    print("=" * 60)
    print("股票管理工具 - 交互模式")
    print("-" * 60)
    print("输入股票代码添加，前缀 '-' 删除（如: -600000）")
    print("按 Ctrl+C 或输入 'q/quit/exit' 退出")
    print("=" * 60)
    print()

    added_count = 0
    removed_count = 0

    try:
        while True:
            try:
                user_input = input("请输入股票代码（6位）: ").strip()

                # 退出命令
                if user_input.lower() in ["q", "quit", "exit"]:
                    print("\n再见！")
                    break

                # 验证输入
                if not user_input:
                    continue

                # 检查是否为删除操作
                is_remove = user_input.startswith("-")
                code = user_input[1:].strip() if is_remove else user_input

                # 验证代码格式
                if not code.isdigit():
                    print("请输入纯数字代码")
                    continue

                if len(code) > 6:
                    print("代码长度不能超过6位")
                    continue

                # 执行添加或删除
                if is_remove:
                    good_df, success = remove_stock_from_good(good_df, code)
                    if success:
                        removed_count += 1
                else:
                    good_df, success = add_stock_to_good(total_df, good_df, code)
                    if success:
                        added_count += 1
                print()

            except KeyboardInterrupt:
                print("\n\n再见！")
                break
            except Exception as e:
                print(f"错误: {e}")
                print()

    except KeyboardInterrupt:
        print("\n\n再见！")

    total_changes = added_count + removed_count
    return good_df, total_changes


def main():
    parser = argparse.ArgumentParser(description="交互式管理好股票列表（添加/删除）")
    parser.add_argument(
        "--stocklist",
        type=Path,
        required=True,
        help="好股票列表CSV路径",
    )

    args = parser.parse_args()
    total_csv = get_file_in_pack("./stocklist.total.csv")

    # 加载数据
    total_df = load_stock_from_file_in_df(total_csv)
    if args.stocklist.exists():
        good_df = load_stock_from_file_in_df(args.stocklist)
    else:
        good_df = pd.DataFrame(columns=total_df.columns)

    # 交互模式
    good_df, changes = interactive_mode(total_df, good_df)

    # 保存结果
    if changes > 0:
        good_df = sort_dataframe(good_df)
        good_df.to_csv(args.stocklist, index=False)
        print(f"📁 已保存到: {args.stocklist}")


if __name__ == "__main__":
    main()
