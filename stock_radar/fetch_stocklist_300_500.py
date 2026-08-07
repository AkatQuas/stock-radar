import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from stock_radar.core.paths import get_file_in_pack
from stock_radar.market.bao_stock_client import BSClient
from stock_radar.market.load_stocklist import (
    load_total_stocklist,
    sort_dataframe,
)


def fetch_300_500():
    with BSClient() as bs:
        df = bs.get_hs300_zz500()
        total = load_total_stocklist(True)
        merged_df = df.merge(
            total,
            on="ts_code",
            how="left",
            suffixes=("_file1", None),  # Add suffixes if name columns differ
        )

        print(merged_df.head())

        merged_df["symbol"] = merged_df["symbol"].fillna(merged_df["symbol_file1"])
        merged_df = merged_df.drop(columns=[col for col in df.columns if col.endswith("_file1")])[
            total.columns
        ]
        return sort_dataframe(merged_df)


def save_with_date(df: pd.DataFrame) -> Path:
    """Save DataFrame to a dated CSV and return the Path."""
    current_date = datetime.now().strftime("%m%d")
    csv_file = get_file_in_pack(f"./stocklist.300_500.{current_date}.csv")
    df.to_csv(csv_file, index=False)
    print(f"Saved to {csv_file}")
    return Path(csv_file)


def main():
    """End-to-end: fetch, save, preview, then optionally replace total file."""
    df = fetch_300_500()
    new_path = save_with_date(df)
    old_path = new_path.with_name("stocklist.300_500.csv")
    shutil.copy2(new_path, old_path)
    print(f"{old_path} is replaced.")
    print(f"{new_path} backup.")


if __name__ == "__main__":
    print("建议半个月执行一次")
    main()
