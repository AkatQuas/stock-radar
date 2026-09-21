"""从 JSON 配置加载选股 / 池选 / 风控策略。"""

from __future__ import annotations

from typing import Any

from stock_radar.core.registry import load_registry


def load_selectors() -> dict[str, Any]:
    """加载 selector.config.json 中的 ``selectors`` 列表。"""
    return load_registry(
        "selector.config.json",
        list_key="selectors",
        module_path="stock_radar.strategy",
    )


def load_risk_selectors() -> dict[str, Any]:
    return load_registry(
        "risk.config.json",
        list_key="risk_selectors",
        module_path="stock_radar.strategy.risk",
    )


def load_pool_selectors() -> dict[str, Any]:
    """加载 pool_selector.config.json 中的股池战法。"""
    return load_registry(
        "pool_selector.config.json",
        list_key="pool_selectors",
        module_path="stock_radar.strategy.pool",
        merge_keys=("pool",),
    )
