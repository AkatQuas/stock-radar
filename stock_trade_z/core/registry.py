"""Shared JSON-config loader for selector / risk-selector registries."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

from stock_trade_z.core.logger import get_logger
from stock_trade_z.core.paths import get_config_path

logger = get_logger("registry")


def load_json_list(cfg_path: Path, list_key: str) -> list[dict[str, Any]]:
    with cfg_path.open(encoding="utf-8") as f:
        cfg_raw = json.load(f)

    if isinstance(cfg_raw, list):
        cfg = cfg_raw
    elif isinstance(cfg_raw, dict) and list_key in cfg_raw:
        cfg = cfg_raw[list_key]
    else:
        cfg = [cfg_raw]

    if not cfg:
        logger.error("%s 未定义任何条目", cfg_path.name)
        sys.exit(1)
    return cfg


def instantiate_from_module(
    module_path: str,
    cfg: dict[str, Any],
) -> tuple[str, Any]:
    cls_name: str | None = cfg.get("class")
    if not cls_name:
        raise ValueError("缺少 class 字段")

    mod_path = cfg.get("module", module_path)
    module = importlib.import_module(mod_path)
    cls = getattr(module, cls_name)
    params = cfg.get("params", {})
    alias = cfg.get("alias", cls_name)
    return alias, cls(**params)


def load_registry(
    config_filename: str,
    list_key: str,
    module_path: str,
) -> dict[str, Any]:
    cfg_path = get_config_path(config_filename)
    entries = load_json_list(cfg_path, list_key)
    result: dict[str, Any] = {}
    for cfg in entries:
        try:
            alias, instance = instantiate_from_module(module_path, cfg)
            if alias in result:
                logger.warning("selector 别名重复，后者覆盖前者: %s", alias)
            result[alias] = instance
        except Exception as e:
            logger.error("跳过配置 %s : %s", cfg.get("alias", cfg.get("class")), e)
    return result
