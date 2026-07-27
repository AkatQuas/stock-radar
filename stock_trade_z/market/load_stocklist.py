from pathlib import Path
from typing import Literal, TypedDict, overload

import pandas as pd

from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.paths import get_file_in_pack


def sort_dataframe(df: pd.DataFrame):
    """对股票数据进行处理和排序。

    将 symbol 列转换为6位数字字符串（不足6位前补0），
    去除重复的 symbol（保留第一条），并按 symbol 升序排序。

    Args:
        df: 包含 symbol 列的 pandas DataFrame

    Returns:
        pd.DataFrame: 处理和排序后的 DataFrame
    """
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df = df.drop_duplicates(subset=["symbol"], keep="first")
    df.sort_values(by="symbol", ascending=True, inplace=True)
    return df


def _filter_stocklist_by_boards(df: pd.DataFrame, exclude_boards: set[str]) -> pd.DataFrame:
    """
    exclude_boards 子集：{'gem','star','bj'}
    - gem  : 创业板 300/301（.SZ）
    - star : 科创板 688（.SH）
    - bj   : 北交所（.BJ 或 4/8 开头）
    """
    code = df["symbol"].astype(str)
    ts_code = df["ts_code"].astype(str).str.upper()
    mask = pd.Series(True, index=df.index)

    if "gem" in exclude_boards:
        mask &= ~code.str.startswith(("300", "301"))
    if "star" in exclude_boards:
        mask &= ~code.str.startswith(("688",))
    if "bj" in exclude_boards:
        mask &= ~(ts_code.str.endswith(".BJ") | code.str.startswith(("4", "8")))

    return df[mask].copy()


class StockCodeDict(TypedDict):
    symbol: str  # 键名：证券代码，类型：字符串
    name: str  # 键名：证券名称，类型：字符串
    xueqiu_url: str  # 雪球页面的地址


def load_stock_from_file_in_df(
    csv_file: Path, exclude_boards: set[str] | None = None
) -> pd.DataFrame:
    """
    读取 stock list csv file & 过滤板块
    """
    if exclude_boards is None:
        exclude_boards = set()
    if not csv_file.exists():
        raise FileNotFoundError(f"csv 文件不存在， {csv_file}")
    df = pd.read_csv(csv_file)
    df = _filter_stocklist_by_boards(df, exclude_boards)
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    return df.drop_duplicates(subset=["symbol"], keep="first")


def load_stock_from_file(csv_file: Path, exclude_boards: set[str]) -> list[StockCodeDict]:
    """
    读取 stock list csv file & 过滤板块
    """
    df = load_stock_from_file_in_df(csv_file, exclude_boards)
    result_list: list[StockCodeDict] = df[["symbol", "name", "xueqiu_url"]].to_dict("records")  # type: ignore

    get_logger("noop").info(
        "从 %s 读取到 %d 只股票（排除板块：%s）",
        csv_file,
        len(result_list),
        ",".join(sorted(exclude_boards)) or "无",
    )
    return result_list


@overload
def load_total_stocklist(need_df: Literal[True]) -> pd.DataFrame: ...


@overload
def load_total_stocklist(need_df: Literal[False] = False) -> list[StockCodeDict]: ...


def load_total_stocklist(need_df: bool = False) -> pd.DataFrame | list[StockCodeDict]:
    """
    Load stock list with flexible return type.

    Args:
        need_df: If True, return a single DataFrame; if False (default), return a dict of DataFrames.

    Returns:
        DataFrame (if need_df=True) or List[StockCodeDict] (if need_df=False)
    """
    total_file = get_file_in_pack("./stocklist.total.csv")
    if need_df:
        return load_stock_from_file_in_df(total_file, set())

    return load_stock_from_file(total_file, set())


def code2ts_code(code: str) -> str:
    """把6位code映射到标准 TuShare code 后缀。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def code2bs_code(code: str) -> str:
    """把6位code映射到标准 BaoStock code 后缀。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"sh.{code}"
    if code.startswith(("4", "8")):
        return f"bj.{code}"
    return f"sz.{code}"
