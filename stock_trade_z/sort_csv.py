import argparse
import warnings
from pathlib import Path

from stock_trade_z.lib.load_stocklist import (
    load_stock_from_file_in_df,
    load_total_stocklist,
    sort_dataframe,
)


def main():
    warnings.warn(
        " sort_csv.py is deprecated and will be removed in a future version. "
        "This functionality is now integrated into other tools.",
        DeprecationWarning,
        stacklevel=2,
    )
    print("=" * 60)
    print(" DEPRECATED: This script is obsolete")
    print("=" * 60)
    print()

    parser = argparse.ArgumentParser(description="对 stocklist.csv 进行排序 (已废弃)")

    parser.add_argument(
        "--stocklist",
        type=Path,
        help="股票清单CSV路径（需含 ts_code 或 symbol）",
    )
    parser.add_argument(
        "--replace",
        action="store_true",  # 默认为 False
        help="替换原文件（默认不启用）",
    )

    args = parser.parse_args()

    csv_file = args.stocklist
    df = load_stock_from_file_in_df(csv_file)
    total = load_total_stocklist(True)

    merged_df = df.merge(
        total,
        on="ts_code",
        how="left",
        suffixes=("_file1", None),
    )
    merged_df = merged_df.drop(columns=[col for col in df.columns if col.endswith("_file1")])[
        total.columns
    ]
    print(merged_df.head())
    df = sort_dataframe(merged_df)

    output_file = csv_file

    if not args.replace:
        output_filename = f"{csv_file.stem}_sorted{csv_file.suffix}"
        output_file = csv_file.parent / output_filename

    df.to_csv(output_file, index=False)
    print(f"文件已成功排序并保存到: {output_file}")


if __name__ == "__main__":
    main()
