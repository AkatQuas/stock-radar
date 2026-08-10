"""DeepSeek API client (OpenAI-compatible chat completions)."""

import os
from collections.abc import Callable
from typing import Any, Literal

from openai.types.chat import ChatCompletionMessage

from stock_radar.llm.langfuse_tracing import (
    APP_TAG,
    llm_round_span,
    observe,
    openai_client,
    set_trace_input,
    set_trace_metadata,
    set_trace_output,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_REASONING_EFFORT = "low"
MAX_COMPLETION_ROUNDS = 5
REASONING_CONTINUATION_PROMPT = (
    "请直接输出完整排序复盘 Markdown 正文，严格按先前要求的格式，不要重复思考过程。"
)
TRUNCATION_CONTINUATION_PROMPT = (
    "上文排序复盘因长度限制尚未写完。请仅输出剩余未写完的部分，"
    "从截断处无缝衔接，不要重复已有内容，不要输出思考过程。"
)
# Backward-compatible alias used in tests.
CONTINUATION_PROMPT = REASONING_CONTINUATION_PROMPT

ContinuationType = Literal["initial", "reasoning", "truncation"]


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


def _finish_reason(response: Any) -> str | None:
    if not response.choices:
        return None
    return getattr(response.choices[0], "finish_reason", None)


def _completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, Any] | ChatCompletionMessage],
    max_tokens: int,
    reasoning_effort: str,
    generation_name: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
        "extra_body": {"thinking": {"type": "enabled"}},
        "name": generation_name,
    }
    if metadata is not None:
        kwargs["metadata"] = metadata
    return kwargs


def _round_trace_snapshot(
    message: ChatCompletionMessage,
    response: Any,
    *,
    accumulated_chars: int,
) -> dict[str, Any]:
    content = _try_extract_content(message)
    reasoning = _reasoning_content(message)
    usage = getattr(response, "usage", None)
    snapshot: dict[str, Any] = {
        "finish_reason": _finish_reason(response),
        "has_content": bool(content),
        "has_reasoning": bool(reasoning),
        "content_chars": len(content) if content else 0,
        "reasoning_chars": len(reasoning) if reasoning else 0,
        "accumulated_chars": accumulated_chars,
    }
    if usage is not None:
        snapshot["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
        snapshot["completion_tokens"] = getattr(usage, "completion_tokens", None)
        snapshot["total_tokens"] = getattr(usage, "total_tokens", None)
    return snapshot


def _round_observation_names(round_no: int, continuation_type: ContinuationType) -> tuple[str, str]:
    return (
        f"deepseek-round-{round_no}-{continuation_type}",
        f"deepseek-generation-{round_no}-{continuation_type}",
    )


def _build_round_metadata(
    *,
    round_no: int,
    continuation_type: ContinuationType,
    message_count: int,
    accumulated_chars: int,
    reasoning_effort: str,
    model: str,
) -> dict[str, Any]:
    return {
        "round": round_no,
        "continuation_type": continuation_type,
        "message_count": message_count,
        "accumulated_chars": accumulated_chars,
        "reasoning_effort": reasoning_effort,
        "model": model,
    }


def _should_continue_reasoning(message: ChatCompletionMessage) -> bool:
    """True when the model produced reasoning but no final answer yet."""
    if _try_extract_content(message):
        return False
    return _reasoning_content(message) is not None


def _should_continue_truncation(
    response: Any,
    accumulated: str,
    *,
    is_complete: Callable[[str], bool] | None,
) -> bool:
    if _finish_reason(response) == "length":
        return True
    return bool(is_complete and accumulated and not is_complete(accumulated))


@observe(name="deepseek-complete")
def complete(
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    is_complete: Callable[[str], bool] | None = None,
) -> str:
    """Call DeepSeek chat completions with multi-round continuation.

    Thinking-mode models may return ``reasoning_content`` without ``content`` on an
    intermediate round; we append that assistant turn and continue the dialog.

    When output hits ``max_tokens`` (``finish_reason == "length"``) or ``is_complete``
    reports missing sections, we request a truncation continuation and concatenate.
    """
    set_trace_input([{"role": "user", "content": prompt}])
    set_trace_metadata(
        model=model,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        langfuse_tags=[APP_TAG],
    )

    messages: list[dict[str, Any] | ChatCompletionMessage] = [{"role": "user", "content": prompt}]
    client = get_client()
    last_message: ChatCompletionMessage | None = None
    accumulated = ""
    continuation_type: ContinuationType = "initial"
    round_no = 0

    for round_idx in range(MAX_COMPLETION_ROUNDS):
        round_no = round_idx + 1
        round_metadata = _build_round_metadata(
            round_no=round_no,
            continuation_type=continuation_type,
            message_count=len(messages),
            accumulated_chars=len(accumulated),
            reasoning_effort=reasoning_effort,
            model=model,
        )
        span_name, generation_name = _round_observation_names(round_no, continuation_type)

        with llm_round_span(name=span_name, metadata=round_metadata) as round_span:
            response = client.chat.completions.create(
                **_completion_kwargs(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                    generation_name=generation_name,
                    metadata=round_metadata,
                )
            )
            message = response.choices[0].message
            last_message = message
            round_snapshot = _round_trace_snapshot(
                message,
                response,
                accumulated_chars=len(accumulated),
            )
            if round_span is not None:
                round_span.update(output=round_snapshot, metadata=round_snapshot)

        content = _try_extract_content(message)
        if content:
            accumulated += content
            if not _should_continue_truncation(response, accumulated, is_complete=is_complete):
                set_trace_output(
                    {
                        "content_chars": len(accumulated),
                        "rounds": round_no,
                        "complete": True,
                    }
                )
                return accumulated

            continuation_type = "truncation"
            messages.append(message)
            messages.append({"role": "user", "content": TRUNCATION_CONTINUATION_PROMPT})
            continue

        if not _should_continue_reasoning(message) or round_idx == MAX_COMPLETION_ROUNDS - 1:
            break

        continuation_type = "reasoning"
        messages.append(message)
        messages.append({"role": "user", "content": REASONING_CONTINUATION_PROMPT})

    if last_message is None:
        raise RuntimeError("DeepSeek returned no choices")
    final = accumulated if accumulated else _extract_content(last_message)
    set_trace_output(
        {
            "content_chars": len(final),
            "rounds": round_no,
            "complete": bool(not is_complete or is_complete(final)),
        }
    )
    return final


def ping(*, model: str = DEFAULT_MODEL) -> None:
    """Lightweight connectivity check — only verifies the API accepts a request."""
    set_trace_input([{"role": "user", "content": "ping"}])
    set_trace_metadata(model=model, langfuse_tags=[APP_TAG])

    response = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=16,
        extra_body={"thinking": {"type": "disabled"}},
    )
    if not response.choices:
        raise RuntimeError("DeepSeek returned no choices")
