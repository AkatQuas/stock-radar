"""Build markdown reports for Lark docx notifications."""

from __future__ import annotations


def build_select_report_md(
    results: list[dict],
    llm_section: str | None = None,
) -> str:
    lines = []
    if not results:
        lines.append("本轮无选股结果。")
    else:
        for block in results:
            lines.append(f"## {block['selector']}（{block['count']}只）")
            lines.append("")
            for stock in block["stocks"]:
                lines.append(f"- {stock['symbol']} {stock['name']} — {stock['url']}")
            lines.append("")
    if llm_section:
        lines.append("## LLM 复盘")
        lines.append("")
        lines.append(llm_section.replace("**", ""))
    return "\n".join(lines).strip()


def build_pool_select_report_md(
    results: list[dict],
    llm_section: str | None = None,
) -> str:
    lines = []
    if not results:
        lines.append("本轮无股池选股结果。")
    else:
        for block in results:
            lines.append(f"## {block['selector']}（{block['count']}只）")
            lines.append("")
            for stock in block["stocks"]:
                tags = stock.get("tags", "")
                tag_txt = f" `{tags}`" if tags else ""
                lines.append(f"- {stock['symbol']} {stock['name']}{tag_txt} — {stock['url']}")
            lines.append("")
    if llm_section:
        lines.append("## LLM 复盘")
        lines.append("")
        lines.append(llm_section.replace("**", ""))
    return "\n".join(lines).strip()


def build_risk_report_md(
    aggregated: dict[str, list[str]],
    stocklist: list,
) -> str:
    lines = []
    if not aggregated:
        lines.append("未检测到风险股票。")
        return "\n".join(lines)

    for code, reasons in sorted(aggregated.items(), key=lambda kv: len(kv[1]), reverse=True):
        info = next((s for s in stocklist if s["symbol"] == code), None)
        if info:
            name = info.get("name", "")
            url = info.get("xueqiu_url", "")
            lines.append(f"## {code} {name}")
            lines.append(f"- 雪球: {url}")
        else:
            lines.append(f"## {code}")
        lines.append(f"- 风险项 ({len(reasons)}): {', '.join(reasons)}")
        lines.append("")
    return "\n".join(lines).strip()
