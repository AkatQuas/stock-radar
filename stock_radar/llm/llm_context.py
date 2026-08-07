"""Build compact JSON context for LLM stock analysis."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from stock_radar.market.trend_context import TrendContext


def summarize_kline(hist: pd.DataFrame, trade_date: pd.Timestamp) -> dict[str, Any]:
    if hist is None or hist.empty:
        return {}
    df = hist[hist["date"] <= trade_date].copy()
    if df.empty:
        return {}

    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")
    last_close = float(close.iloc[-1])
    summary: dict[str, Any] = {
        "last_close": round(last_close, 2),
        "bars": len(df),
    }

    if len(close) >= 2:
        summary["pct_chg_1d"] = round(float(close.pct_change().iloc[-1] * 100), 2)
    if len(close) >= 6:
        summary["pct_chg_5d"] = round(float((close.iloc[-1] / close.iloc[-6] - 1) * 100), 2)
    if len(volume) >= 6:
        avg5 = float(volume.iloc[-6:-1].mean())
        if avg5 > 0:
            summary["volume_ratio_5d"] = round(float(volume.iloc[-1] / avg5), 2)
    if len(close) >= 20:
        ma20 = float(close.tail(20).mean())
        if ma20 > 0:
            summary["dist_ma20_pct"] = round(float((last_close / ma20 - 1) * 100), 2)
        summary["high_20d"] = bool(last_close >= float(close.tail(20).max()))

    return summary


def _pool_fields(meta: dict) -> dict[str, Any]:
    keys = (
        "pool",
        "lbc",
        "fbt",
        "lbt",
        "zj",
        "zbc",
        "zs",
        "nh",
        "lb",
        "hs",
        "zf",
        "tj",
        "tj_days",
        "tj_boards",
        "p",
        "ztp",
    )
    return {k: meta[k] for k in keys if k in meta and meta[k] is not None}


def build_pick_records(
    *,
    track: str,
    trade_date: pd.Timestamp,
    results: list[dict],
    data: dict[str, pd.DataFrame],
    trend_ctx: TrendContext | None = None,
    risk_by_symbol: dict[str, list[str]] | None = None,
    market_context: dict[str, Any] | None = None,
    max_stocks: int = 20,
) -> list[dict[str, Any]]:
    """Flatten selector results into per-symbol records for LLM."""
    by_symbol: dict[str, dict[str, Any]] = {}

    for block in results:
        selector_name = block.get("selector", "")
        for stock in block.get("stocks", []):
            sym = str(stock["symbol"]).zfill(6)
            entry = by_symbol.setdefault(
                sym,
                {
                    "symbol": sym,
                    "name": stock.get("name", ""),
                    "track": track,
                    "matched_selectors": [],
                    "url": stock.get("url", ""),
                },
            )
            entry["matched_selectors"].append(selector_name)

    ranked = sorted(
        by_symbol.items(),
        key=lambda kv: len(kv[1]["matched_selectors"]),
        reverse=True,
    )
    records: list[dict[str, Any]] = []
    for sym, entry in ranked[:max_stocks]:
        hist = data.get(sym)
        entry["kline_summary"] = summarize_kline(hist, trade_date) if hist is not None else {}
        if trend_ctx is not None:
            meta = trend_ctx.meta_for(sym)
            if meta:
                entry["pool_fields"] = _pool_fields(meta)
        if risk_by_symbol and sym in risk_by_symbol:
            entry["risk_flags"] = risk_by_symbol[sym]
        records.append(entry)

    if market_context:
        for r in records:
            r["market_context"] = market_context

    return records


def picks_to_json(records: list[dict[str, Any]], trade_date: pd.Timestamp) -> str:
    payload = {
        "trade_date": str(trade_date.date()),
        "picks": records,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
