#!/usr/bin/env python3
"""
Script to add xueqiu.com URLs to stocklist.csv

Usage:
    python add_xueqiu_urls.py [--output OUTPUT_FILE] [--preview N]

Options:
    --output OUTPUT_FILE    Save results to this file (default: stocklist_with_urls.csv)
    --preview N            Show first N rows instead of saving (default: 10)
"""

import argparse
from pathlib import Path

import pandas as pd

from stock_trade_z.market.xueqiu import add_xueqiu_url_to_dataframe


def main():
    parser = argparse.ArgumentParser(description="Add xueqiu URLs to stocklist.csv")
    parser.add_argument(
        "--output",
        type=str,
        default="stocklist_with_urls.csv",
        help="Output file path (default: stocklist_with_urls.csv)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=None,
        help="Preview first N rows instead of saving",
    )
    parser.add_argument(
        "--input",
        type=str,
        default="stocklist.csv",
        help="Input CSV file (default: stocklist.csv)",
    )

    args = parser.parse_args()

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"Error: Input file '{input_file}' not found")
        return 1

    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} stocks")

    print("Adding xueqiu URLs...")
    df_with_urls = add_xueqiu_url_to_dataframe(df)

    if args.preview:
        print(f"\nPreview of first {args.preview} rows:")
        print("=" * 80)
        preview_df = df_with_urls.head(args.preview)
        print(preview_df[["ts_code", "symbol", "name", "xueqiu_url"]].to_string(index=False))
        print("=" * 80)
        print(f"\nTotal stocks: {len(df_with_urls)}")
    else:
        output_file = Path(args.output)
        print(f"Saving to {output_file}...")
        df_with_urls.to_csv(output_file, index=False)
        print(f"✓ Successfully saved {len(df_with_urls)} stocks to {output_file}")

    return 0


if __name__ == "__main__":
    exit(main())
