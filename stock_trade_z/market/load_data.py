from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from stock_trade_z.core.logger import get_logger

logger = get_logger("select")


def load_data(data_dir: Path, codes: Iterable[str]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for code in codes:
        fp = data_dir / f"{code}.csv"
        if not fp.exists():
            logger.warning("%s 不存在，跳过", fp.name)
            continue
        try:
            df = pd.read_csv(fp, parse_dates=["date"]).sort_values("date")
        except Exception as e:
            # 捕获其他未预期的异常，避免循环中断
            logger.error("%s 加载失败：%s，跳过", fp.name, str(e))
            continue
        frames[code] = df
    return frames
