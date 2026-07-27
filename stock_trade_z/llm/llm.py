"""DeepSeek API client (OpenAI-compatible chat completions)."""

import os

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MODEL = "deepseek-v4-flash"


def api_key_configured() -> bool:
    return bool(os.getenv(API_KEY_ENV))


def get_client() -> OpenAI:
    api_key = os.getenv(API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"{API_KEY_ENV} is not set")
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def _reasoning_preview(message: ChatCompletionMessage) -> str | None:
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning is None:
        reasoning = (getattr(message, "model_extra", None) or {}).get("reasoning_content")
    if not reasoning:
        return None
    text = str(reasoning).strip()
    return text[:80] + "…" if len(text) > 80 else text


def _extract_content(message: ChatCompletionMessage) -> str:
    """Return final assistant output (never reasoning trace)."""
    text = (message.content or "").strip()
    if text:
        return text

    extra = getattr(message, "model_extra", None) or {}
    text = (extra.get("content") or "").strip()
    if text:
        return text

    hint = _reasoning_preview(message)
    if hint:
        raise RuntimeError(
            f"DeepSeek returned reasoning only (no final content), e.g. {hint!r}. "
            "Use deepseek-v4-flash for digests, or raise digest.max_tokens for reasoner models."
        )
    raise RuntimeError("DeepSeek returned empty content")


def complete(prompt: str, *, model: str, max_tokens: int) -> str:
    response = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return _extract_content(response.choices[0].message)


def ping(*, model: str = DEFAULT_MODEL) -> None:
    """Lightweight connectivity check — only verifies the API accepts a request."""
    response = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=16,
    )
    if not response.choices:
        raise RuntimeError("DeepSeek returned no choices")
