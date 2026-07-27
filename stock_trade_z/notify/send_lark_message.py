import json
import os
import time
from pathlib import Path

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateMessageResponse,
)

load_dotenv(Path("./.env"))


_client: lark.Client | None = None


def lark_configured() -> bool:
    return bool(os.getenv("LARK_APP_ID") and os.getenv("LARK_SECRET") and os.getenv("ME_UNION_ID"))


def get_client() -> lark.Client:
    """Initialize and return the Lark client."""
    global _client
    if _client is None:
        _client = (
            lark.Client.builder()
            .app_id(os.getenv("LARK_APP_ID"))
            .app_secret(os.getenv("LARK_SECRET"))
            .log_level(lark.LogLevel.INFO)
            .build()
        )
    return _client


def build_interactive_card(
    title: str,
    fields: list[dict],
    template: str = "wathet",
    actions: list[dict] | None = None,
) -> dict:
    """
    Build an interactive card message structure.

    Args:
        title: Card header title
        fields: List of field dicts with "is_short" (bool) and "content" (str)
        template: Card Template, blue -> info, wathet -> info, green -> success, yellow -> warn, carmine -> error, grey -> disable
        actions: Optional list of action button dicts with "text", "type", "value"

    Returns:
        Card JSON structure dict
    """
    elements = [
        {
            "tag": "div",
            "fields": [
                {"is_short": f["is_short"], "text": {"tag": "lark_md", "content": f["content"]}}
                for f in fields
            ],
        }
    ]

    if actions:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": a["text"]},
                        "type": a.get("type", "primary"),
                        "value": a.get("value", {}),
                    }
                    for a in actions
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "template": template, "content": title}},
        "elements": elements,
    }


def send_message(
    receive_id: str,
    content: dict | str,
    msg_type: str = "text",
    max_retries: int = 3,
    retry_interval: int = 10,
) -> bool:
    """
    Send a message to a Lark user with retry logic.

    Args:
        receive_id: The union_id of the recipient
        content: A JSON-serializable dict or string for the message content
        msg_type: Message type - "text" or "interactive" (default "text")
        max_retries: Maximum number of retry attempts (default 3)
        retry_interval: Seconds to wait between retries (default 10)

    Returns:
        True if successful, False otherwise
    """
    client = get_client()

    # For interactive card, content should be JSON string of the card structure
    if msg_type == "interactive":
        content_str = json.dumps(content) if isinstance(content, dict) else content
    else:
        # For text message, wrap in {"text": ...} format
        content_str = json.dumps(content) if isinstance(content, dict) else content

    request: CreateMessageRequest = (
        CreateMessageRequest.builder()
        .receive_id_type("union_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(msg_type)
            .content(content_str)
            .build()
        )
        .build()
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response: CreateMessageResponse = client.im.v1.message.create(request)

            if not response.success():
                last_error = (
                    f"code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
                )
                lark.logger.warning(f"Attempt {attempt}/{max_retries} failed: {last_error}")
            else:
                lark.logger.info(lark.JSON.marshal(response.data, indent=4))
                return True

        except Exception as e:
            last_error = str(e)
            lark.logger.warning(f"Attempt {attempt}/{max_retries} raised exception: {e}")

        if attempt < max_retries:
            lark.logger.info(f"Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)

    lark.logger.error(f"All {max_retries} attempts failed. Last error: {last_error}")
    return False


def main():
    send_message(receive_id=os.getenv("ME_UNION_ID"), content={"text": "test content"})


if __name__ == "__main__":
    main()
