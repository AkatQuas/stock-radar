import os
from pathlib import Path

from dotenv import load_dotenv

_zhitu_token: str | None = None


def set_zhitu_token(token: str) -> str:
    """由外部(比如测试)注入已配置好的 token"""
    global _zhitu_token
    if _zhitu_token is not None:
        raise Exception("zhitu token is already set, can not set twice")
    _zhitu_token = token
    return _zhitu_token


def get_zhitu_token() -> str:
    global _zhitu_token
    if _zhitu_token is None:
        # .env is relative to `cwd`
        load_dotenv(Path("./.env"))
        _zhitu_token = os.environ.get("ZHITU_TOKEN")
        if not _zhitu_token:
            raise ValueError("请先设置环境变量 ZHITU_TOKEN，例如：export ZHITU_TOKEN=你的token")
    return _zhitu_token
