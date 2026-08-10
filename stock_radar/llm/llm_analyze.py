"""LLM rank + explain + second-opinion for selector shortlists."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from stock_radar.core.logger import get_logger
from stock_radar.llm.langfuse_tracing import APP_TAG, observe, set_trace_metadata
from stock_radar.llm.llm import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    api_key_configured,
    complete,
)

logger = get_logger("select")

ANALYZE_MAX_TOKENS = 4096


@observe(name="analyze-picks", capture_input=False)
def analyze_picks(
    records: list[dict[str, Any]],
    trade_date: pd.Timestamp,
    *,
    track: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = ANALYZE_MAX_TOKENS,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> str | None:
    """Rank and annotate picks; returns Lark-ready markdown or None on failure."""
    if not api_key_configured():
        logger.warning("DEEPSEEK_API_KEY 未设置，跳过 LLM 分析")
        return None
    if not records:
        return None

    set_trace_metadata(
        model=model,
        track=track,
        pick_count=len(records),
        trade_date=str(trade_date.date()),
        langfuse_tags=[APP_TAG],
    )

    payload = {"trade_date": str(trade_date.date()), "track": track, "picks": records}
    picks_json = json.dumps(payload, ensure_ascii=False, indent=2)

    prompt = f"""你是 A 股短线选股研究员，为人工复盘提供第二意见（非投资建议）。

以下是由规则选股器产生的候选列表（track={track}）。请根据结构化数据：
1. 按短期质量重新排序（rank 从 1 开始）
2. 为每只给出 verdict: keep（推荐）| flag（谨慎）| veto（建议剔除）
3. 用中文简述理由（1-2 句）和主要风险

仅根据提供的结构化数据判断，不要编造新闻或财报。
直接输出可粘贴进 Lark 文档的 Markdown 正文（不要代码块、不要 JSON、不要前言后记），格式模版为： `[code name](xueqiu url) [verdict]: reason` 。若干示例：

### 排序推荐
- [600000 浦发银行](https://xueqiu.com/S/SH600000) [keep] 连板强势，封板早 — 风险: 高位换手
- [000001 平安银行](https://xueqiu.com/S/SZ000001) [flag] 量能尚可但贴近涨停 — 风险: 分歧加大

### 建议剔除
- [000002 万科A](https://xueqiu.com/S/SZ000002) [veto] 换手过高且趋势走弱

候选数据：
{picks_json}"""

    try:
        return complete(
            prompt,
            model=model,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ).strip()
    except Exception as e:
        logger.error("LLM 分析失败: %s", e)
        return None
