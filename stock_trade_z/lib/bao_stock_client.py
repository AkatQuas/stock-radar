"""
http://www.baostock.com/mainContent?file=stockKData.md
"""

import time

import baostock as bs
import pandas as pd

from .constant import COLUMNS
from .load_stocklist import code2bs_code
from .logger import get_logger
from .time import validate


class BSClient:
    def __init__(self):
        """初始化客户端"""
        self._lg = None
        self.is_logged_in = False

    def login(self):
        """
        登录baostock

        返回:
            bool: 登录是否成功
        """
        if self.is_logged_in:
            return True

        self._lg = bs.login()

        if self._lg.error_code == "0":
            self.is_logged_in = True
            return True
        raise RuntimeError(f"登录失败: {self._lg.error_msg}")

    def logout(self):
        """登出baostock"""
        if self.is_logged_in:
            bs.logout()
            self.is_logged_in = False
            self._lg = None

    def __enter__(self):
        """上下文管理器入口"""
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.logout()

    # ===数据获取方法 ===

    def get_kline_baostock(
        self, code: str, start: str, end: str | None = None
    ) -> pd.DataFrame | None:
        """
        下载股票数据

        参数:
            code: 股票代码 (如: 600000, 000001)
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)

        返回:
            DataFrame: 股票数据，失败返回None
        """
        if not self.is_logged_in and not self.login():
            return None

        bs_code = code2bs_code(code)
        # fields = "date,open,high,low,close,preclose,volume,amount,adjustflag,turn,pctChg",
        fields = "date,open,close,high,low,volume,amount,turn,pctChg"
        rs = bs.query_history_k_data_plus(
            bs_code, fields, start_date=start, end_date=end, frequency="d", adjustflag="2"
        )
        if rs is None:
            return None

        data_list = []
        while (rs.error_code == "0") & rs.next():
            # 获取一条记录，将记录合并在一起
            data_list.append(rs.get_row_data())
        df = pd.DataFrame(data_list, columns=rs.fields)
        df = df.rename(columns={"pctChg": "pct_chg"})[COLUMNS].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ["open", "high", "low", "close", "turn", "pct_chg"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(2)
        # 成交量：整数（手），先填充 NaN 为 0 再转换
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        # 成交额：保留2位小数（元），NaN 填充为 0
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).round(2)
        return df.sort_values("date").reset_index(drop=True)

    def fetch_one_data(self, code: str, start: str, end: str | None = None) -> pd.DataFrame | None:
        """
        .. deprecated::
        """
        if not self.is_logged_in and not self.login():
            return None

        logger = get_logger("fetch")
        for attempt in range(1, 4):
            try:
                new_df = self.get_kline_baostock(code, start, end)
                if new_df is None:
                    logger.debug("%s 无数据，生成空表。", code)
                    new_df = pd.DataFrame(columns=COLUMNS)
                return validate(new_df)
            except Exception as e:
                silent_seconds = 15 * attempt
                logger.info(f"{code} 第 {attempt} 次抓取失败: {e}. \n{silent_seconds} 秒后重试")
                time.sleep(silent_seconds)
        else:
            return None

    def get_hs300_zz500(self):
        df1 = self.get_hs300()
        df2 = self.get_zz500()
        combined_df = pd.concat([df1, df2], ignore_index=True)

        combined_df.drop_duplicates(subset=["ts_code"], keep="first", inplace=True)
        return combined_df

    def get_hs300(self):
        self.login()
        rs = bs.query_hs300_stocks()

        stocks = []
        tick = 0
        while (rs.error_code == "0") & rs.next():
            stocks.append(rs.get_row_data())
            time.sleep(0.1)
            tick += 1
            print(f"hs300 _ {tick}")
            if tick > 5:
                break

        df = pd.DataFrame(stocks, columns=rs.fields)
        return self._polish_to_tushare(df)

    def get_zz500(self):
        self.login()
        rs = bs.query_zz500_stocks()

        stocks = []
        tick = 0
        while (rs.error_code == "0") & rs.next():
            stocks.append(rs.get_row_data())
            time.sleep(0.1)
            tick += 1
            print(f"zz500 _ {tick}")
            if tick > 4:
                break

        df = pd.DataFrame(stocks, columns=rs.fields)
        return self._polish_to_tushare(df)

    @staticmethod
    def _polish_to_tushare(df: pd.DataFrame):
        """
        baostock 的数据清理成 tushare 的样子
        """
        split_code = df["code"].str.split(".", expand=True)
        df["ts_code"] = split_code[1] + "." + split_code[0].str.upper()
        df["symbol"] = split_code[1].astype(str).str.zfill(6)
        df = df.rename(columns={"code_name": "name"})
        df.drop(columns=["code", "updateDate"], inplace=True)
        print(df.head())
        return df[["ts_code", "symbol", "name"]]
