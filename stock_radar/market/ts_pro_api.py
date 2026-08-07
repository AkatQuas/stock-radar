import os
from pathlib import Path
from typing import Any

import tushare as ts
from dotenv import load_dotenv

pro_api: Any | None = None  # 模块级会话


def set_pro_api(session) -> None:
    """由外部(比如GUI)注入已创建好的 ts.pro_api() 会话"""
    global pro_api
    if pro_api is not None:
        raise Exception("ts_api is already set, can not set twice")
    pro_api = session
    return pro_api


def get_pro_api():
    global pro_api
    if pro_api is None:
        # .env is relative to `cwd`
        load_dotenv(Path("./.env"))
        ts_token = os.environ.get("TUSHARE_TOKEN")
        if not ts_token:
            raise ValueError("请先设置环境变量 TUSHARE_TOKEN，例如：export TUSHARE_TOKEN=你的token")
        ts.set_token(ts_token)

        os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
        os.environ["no_proxy"] = os.environ["NO_PROXY"]
        pro_api = ts.pro_api()
    return pro_api
