"""Unified risk detection orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from stock_radar.core.logger import get_logger
from stock_radar.notify.lark_notify import send_report_as_doc
from stock_radar.notify.lark_report import build_risk_report_md
from stock_radar.strategy.base import run_select

logger = get_logger("risk")


@dataclass
class RiskOptions:
    send_lark: bool = False


@dataclass
class RiskResult:
    trade_date: pd.Timestamp
    per_selector_hits: dict[str, list[str]]
    aggregated: dict[str, list[str]]


def run_risk_detection(
    *,
    selectors: dict[str, Any],
    data: dict[str, pd.DataFrame],
    trade_date: pd.Timestamp,
    stocklist: list[dict],
    opts: RiskOptions,
    report_title: str | None = None,
    report_summary: str | None = None,
) -> RiskResult:
    """Run risk selectors with per-selector error isolation and optional Lark report."""
    per_selector_hits: dict[str, list[str]] = {}
    aggregated: dict[str, list[str]] = {}

    for name, sel in selectors.items():
        try:
            hits = run_select(sel, trade_date, data)
        except Exception:
            logger.exception("selector %s raised", name)
            hits = []
        per_selector_hits[name] = hits
        for code in hits:
            aggregated.setdefault(code, []).append(name)

    if aggregated:
        header = f"===Aggregated risk summary ({len(aggregated)} symbols) ==="
        out_lines: list[str] = [header]
        for code, reasons in sorted(aggregated.items(), key=lambda kv: len(kv[1]), reverse=True):
            info = next((s for s in stocklist if s["symbol"] == code), None)
            if info:
                name = info.get("name", "")
                name_padded = name.ljust(5)
                url = info.get("xueqiu_url", "")
                out_lines.append(
                    f"{code}, {name_padded}({url}) => {len(reasons)} flags: {', '.join(reasons)}"
                )
            else:
                out_lines.append(f"{code} => {len(reasons)} flags: {', '.join(reasons)}")
        logger.info("\n%s", "\n".join(out_lines))
    else:
        logger.info("No risky symbols detected by selectors.")

    if opts.send_lark and report_title and report_summary:
        markdown = build_risk_report_md(aggregated, stocklist)
        if send_report_as_doc(title=report_title, markdown=markdown, summary=report_summary):
            logger.info("已发送风险检测报告文档链接到 Lark")
        else:
            logger.error("发送 Lark 通知失败")

    return RiskResult(
        trade_date=trade_date,
        per_selector_hits=per_selector_hits,
        aggregated=aggregated,
    )
