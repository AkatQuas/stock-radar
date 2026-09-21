"""Unified selection orchestration for K-line and pool tracks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from stock_radar.core.logger import get_logger
from stock_radar.llm.llm_analyze import analyze_picks
from stock_radar.llm.llm_context import build_pick_records
from stock_radar.market.trend_context import TrendContext
from stock_radar.notify.lark_notify import send_report_as_doc
from stock_radar.strategy.base import run_select

logger = get_logger("select")


@dataclass
class SelectionOptions:
    llm_analyze: bool = False
    llm_max: int = 20
    send_lark: bool = False
    track: str = "normal"


@dataclass
class SelectionResult:
    trade_date: pd.Timestamp
    results: list[dict[str, Any]]
    llm_section: str | None = None


def _enrich_stock(
    sym: str,
    stocklist_by_sym: dict[str, dict],
    *,
    tags: str = "",
) -> dict[str, Any]:
    info = stocklist_by_sym.get(sym, {"symbol": sym, "name": sym, "xueqiu_url": ""})
    stock: dict[str, Any] = {
        "symbol": sym,
        "name": info.get("name", sym),
        "url": info.get("xueqiu_url", ""),
    }
    if tags:
        stock["tags"] = tags
    return stock


def run_selection(
    *,
    selectors: dict[str, Any],
    data: dict[str, pd.DataFrame],
    trade_date: pd.Timestamp,
    stocklist: list[dict],
    opts: SelectionOptions,
    pools: dict[str, pd.DataFrame] | None = None,
    trend_ctx: TrendContext | None = None,
    tag_fn: Callable[[str], str] | None = None,
    market_context: dict[str, Any] | None = None,
    report_title: str | None = None,
    report_summary: str | None = None,
    build_report_md: Callable[[list[dict], str | None], str] | None = None,
) -> SelectionResult:
    """Run selectors, optional LLM analyze, optional Lark notification."""
    stock_by_sym = {s["symbol"]: s for s in stocklist}
    all_results: list[dict[str, Any]] = []

    for alias, selector in selectors.items():
        picks = run_select(selector, trade_date, data, pools=pools)
        if not picks:
            logger.info("===[%s] 无结果===", alias)
            continue

        logger.info("===[%s] 选股结果 (%d)===", alias, len(picks))
        stocks = []
        for sym in picks:
            tags = tag_fn(sym) if tag_fn else ""
            stock = _enrich_stock(sym, stock_by_sym, tags=tags)
            stocks.append(stock)
            if tags:
                logger.info("%s %s %s", sym, stock["name"], tags)
            else:
                logger.info("%s %s", sym, stock["name"])

        all_results.append({"selector": alias, "count": len(picks), "stocks": stocks})

    llm_section = None
    if opts.llm_analyze and all_results:
        records = build_pick_records(
            track=opts.track,
            trade_date=trade_date,
            results=all_results,
            data=data,
            trend_ctx=trend_ctx,
            market_context=market_context,
            max_stocks=opts.llm_max,
        )
        llm_section = analyze_picks(records, trade_date, track=opts.track)

    if opts.send_lark and build_report_md and report_title and report_summary:
        markdown = build_report_md(all_results, llm_section)
        if send_report_as_doc(title=report_title, markdown=markdown, summary=report_summary):
            logger.info("已发送报告文档链接到 Lark")
        else:
            logger.error("发送 Lark 失败")

    return SelectionResult(trade_date=trade_date, results=all_results, llm_section=llm_section)
