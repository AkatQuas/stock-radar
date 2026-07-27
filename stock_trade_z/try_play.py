from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts

from stock_trade_z.core.compute import compute_cci14_cci84, compute_pit_and_trap
from stock_trade_z.market.bao_stock_client import BSClient
from stock_trade_z.market.load_stocklist import load_stock_from_file_in_df
from stock_trade_z.market.ts_pro_api import get_pro_api

if __name__ == "__main__":
    arr = np.array([[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11, 12, 13, 14]])
    print(arr.ndim, arr.shape)
    arr_3d = np.array([[[1, 2], [3, 4]], [[5, 6], [7, 8]]])
    print(arr_3d.ndim, arr_3d.shape)
    x = np.linspace(0, 2 * np.pi, 100)  # useful to evaluate function at lots of points
    f = np.sin(x)
    print(x, f)
    # api = get_pro_api()
    # df = ts.pro_bar(
    #     ts_code="002549.SZ",
    #     start_date="20260101",
    #     freq="D",
    #     adj="qfq",
    #     api=api,
    # )
    # df = df[["trade_date", "open", "close", "high", "low", "vol", "amount"]].copy()
