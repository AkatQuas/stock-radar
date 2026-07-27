"""从 JSON 配置加载选股 / 池选 / 风控策略。"""

from __future__ import annotations

import importlib
from typing import Any

from stock_trade_z.core.paths import get_config_path
from stock_trade_z.core.registry import load_json_list, load_registry


def load_selectors() -> dict[str, Any]:
    """加载 selector.config.json 中的 ``selectors`` 列表。"""
    return load_registry(
        "selector.config.json",
        list_key="selectors",
        module_path="stock_trade_z.strategy",
    )


def load_risk_selectors() -> dict[str, Any]:
    return load_registry(
        "risk.config.json",
        list_key="risk_selectors",
        module_path="stock_trade_z.strategy.risk",
    )


def load_pool_selectors() -> dict[str, Any]:
    cfg_path = get_config_path("pool_selector.config.json")
    entries = load_json_list(cfg_path, "pool_selectors")
    module = importlib.import_module("stock_trade_z.strategy.pool")
    result: dict[str, Any] = {}

    for cfg in entries:
        cls_name = cfg.get("class")
        if not cls_name:
            continue
        cls = getattr(module, cls_name)
        params = dict(cfg.get("params") or {})
        pool = cfg.get("pool")
        if pool and "pool" not in params:
            params["pool"] = pool
        alias = cfg.get("alias", cls_name)
        result[alias] = cls(**params)

    return result
