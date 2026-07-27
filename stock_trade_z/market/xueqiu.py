import pandas as pd


def ts_code_to_xueqiu_url(ts_code: str) -> str:
    """
    Convert ts_code format to xueqiu.com URL.

    Args:
        ts_code: Stock code in format "XXXXXX.XX" (e.g., "000001.SZ", "688345.SH")

    Returns:
        URL string in format "https://xueqiu.com/S/{EXCHANGE}{CODE}"

    Example:
        >>> ts_code_to_xueqiu_url("000001.SZ")
        'https://xueqiu.com/S/SZ000001'
        >>> ts_code_to_xueqiu_url("688345.SH")
        'https://xueqiu.com/S/SH688345'
    """
    stock_number, exchange_code = ts_code.split(".")
    return f"https://xueqiu.com/S/{exchange_code}{stock_number}"


def add_xueqiu_url_to_dataframe(df: pd.DataFrame, ts_code_column: str = "ts_code") -> pd.DataFrame:
    """
    Add a xueqiu_url column to a DataFrame containing ts_code.

    Args:
        df: DataFrame with ts_code column
        ts_code_column: Name of the column containing ts_code (default: "ts_code")

    Returns:
        DataFrame with added xueqiu_url column

    Example:
        >>> df = pd.DataFrame({"ts_code": ["000001.SZ", "688345.SH"]})
        >>> df = add_xueqiu_url_to_dataframe(df)
        >>> df["xueqiu_url"].tolist()
        ['https://xueqiu.com/S/SZ000001', 'https://xueqiu.com/S/SH688345']
    """
    df = df.copy()
    df["xueqiu_url"] = df[ts_code_column].apply(ts_code_to_xueqiu_url)
    return df
