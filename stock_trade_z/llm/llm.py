"""DeepSeek API client (OpenAI-compatible chat completions)."""

import os
from typing import Any

from openai.types.chat import ChatCompletionMessage

from stock_trade_z.llm.langfuse_tracing import (
    APP_TAG,
    observe,
    openai_client,
    set_trace_input,
    set_trace_metadata,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MODEL = "deepseek-v4-flash"
MAX_COMPLETION_ROUNDS = 3
CONTINUATION_PROMPT = (
    "请直接输出完整排序复盘 Markdown 正文，严格按先前要求的格式，不要重复思考过程。"
)


def api_key_configured() -> bool:
    return bool(os.getenv(API_KEY_ENV))


def get_client():
    api_key = os.getenv(API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"{API_KEY_ENV} is not set")
    return openai_client(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def _reasoning_content(message: ChatCompletionMessage) -> str | None:
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning is None:
        reasoning = (getattr(message, "model_extra", None) or {}).get("reasoning_content")
    if not reasoning:
        return None
    text = str(reasoning).strip()
    return text or None


def _reasoning_preview(message: ChatCompletionMessage) -> str | None:
    text = _reasoning_content(message)
    if not text:
        return None
    return text[:80] + "…" if len(text) > 80 else text


def _try_extract_content(message: ChatCompletionMessage) -> str | None:
    """Return final assistant output, or None if only reasoning / empty."""
    text = (message.content or "").strip()
    if text:
        return text

    extra = getattr(message, "model_extra", None) or {}
    text = (extra.get("content") or "").strip()
    if text:
        return text
    return None


def _extract_content(message: ChatCompletionMessage) -> str:
    """Return final assistant output (never reasoning trace)."""
    content = _try_extract_content(message)
    if content:
        return content

    hint = _reasoning_preview(message)
    if hint:
        raise RuntimeError(
            f"DeepSeek returned reasoning only (no final content) after "
            f"{MAX_COMPLETION_ROUNDS} round(s), e.g. {hint!r}. "
            "Raise max_tokens or switch to a non-thinking model."
        )
    raise RuntimeError("DeepSeek returned empty content")


def _should_continue(message: ChatCompletionMessage) -> bool:
    """True when the model produced reasoning but no final answer yet."""
    if _try_extract_content(message):
        return False
    return _reasoning_content(message) is not None


@observe(name="deepseek-complete")
def complete(prompt: str, *, model: str, max_tokens: int) -> str:
    """Call DeepSeek chat completions, retrying up to MAX_COMPLETION_ROUNDS.

    Thinking-mode models may return ``reasoning_content`` without ``content`` on an
    intermediate round; we append that assistant turn and continue the dialog.
    """
    set_trace_input([{"role": "user", "content": prompt}])
    set_trace_metadata(model=model, max_tokens=max_tokens, langfuse_tags=[APP_TAG])

    messages: list[dict[str, Any] | ChatCompletionMessage] = [{"role": "user", "content": prompt}]
    client = get_client()
    last_message: ChatCompletionMessage | None = None

    for round_idx in range(MAX_COMPLETION_ROUNDS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            name="deepseek-chat-completion",
            metadata={"round": round_idx + 1},
        )
        message = response.choices[0].message
        last_message = message

        content = _try_extract_content(message)
        if content:
            return content

        if not _should_continue(message) or round_idx == MAX_COMPLETION_ROUNDS - 1:
            break

        # Preserve reasoning_content so the model can continue the same turn.
        messages.append(message)
        messages.append({"role": "user", "content": CONTINUATION_PROMPT})

    if last_message is None:
        raise RuntimeError("DeepSeek returned no choices")
    return _extract_content(last_message)


@observe(name="deepseek-ping", capture_output=False)
def ping(*, model: str = DEFAULT_MODEL) -> None:
    """Lightweight connectivity check — only verifies the API accepts a request."""
    set_trace_input([{"role": "user", "content": "ping"}])
    set_trace_metadata(model=model, langfuse_tags=[APP_TAG])

    response = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=16,
        name="deepseek-ping",
    )
    if not response.choices:
        raise RuntimeError("DeepSeek returned no choices")
