from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_trade_z.market.load_data import load_data


def load_data_folder(
    data_dir: Path, date: str | None = None
) -> tuple[dict[str, pd.DataFrame], pd.Timestamp]:
    """Load CSV files from `data_dir` and normalize their `date` column.

    Parameters
    - data_dir: path to folder containing CSV K-line files
    - date: optional date string; if None, the latest date across data is returned

    Returns: (data_dict, trade_date)
    """
    files = [f.stem for f in data_dir.glob("*.csv")]

    if len(files) == 0:
        raise FileNotFoundError("no files found in data_dir")

    data = load_data(data_dir, files)
    if not data:
        raise RuntimeError("failed to load any data from data_dir")

    # normalize date column to pandas.Timestamp
    for df in data.values():
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    trade_date = pd.to_datetime(date) if date else max(df["date"].max() for df in data.values())

    return data, trade_date
