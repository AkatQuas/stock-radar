"""Send Lark notifications as docx link + short text message."""

from __future__ import annotations

import os

from stock_trade_z.core.logger import get_logger
from stock_trade_z.notify.lark_doc import create_doc_with_markdown
from stock_trade_z.notify.send_lark_message import lark_configured, send_message

logger = get_logger("noop")


def send_report_as_doc(
    *,
    title: str,
    markdown: str,
    summary: str | None = None,
    receive_id: str | None = None,
) -> bool:
    """
    Create a Lark docx with markdown body, then send bot message with doc link.

    Returns True if the bot message was sent successfully.
    """
    if not lark_configured():
        logger.warning("Lark 未配置，跳过通知")
        return False

    recipient = receive_id or os.getenv("ME_UNION_ID")
    if not recipient:
        logger.warning("ME_UNION_ID 未配置，跳过通知")
        return False

    try:
        doc_url = create_doc_with_markdown(
            title,
            markdown,
            recipient_union_id=recipient,
        )
    except Exception as e:
        logger.error("创建 Lark 文档失败: %s", e)
        return False

    intro = summary or title
    text = f"{intro}\n\n📄 详细报告: {doc_url}"
    return send_message(recipient, {"text": text}, msg_type="text")
