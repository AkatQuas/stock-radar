"""Optional Langfuse tracing for OpenAI-compatible clients.

No-op when ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are unset.
"""

from __future__ import annotations

import atexit
import os
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

PUBLIC_KEY_ENV = "LANGFUSE_PUBLIC_KEY"
SECRET_KEY_ENV = "LANGFUSE_SECRET_KEY"
APP_TAG = "stock-trade-z"


def is_enabled() -> bool:
    return bool(os.getenv(PUBLIC_KEY_ENV) and os.getenv(SECRET_KEY_ENV))


def observe(
    *,
    name: str,
    as_type: str = "span",
    capture_input: bool = False,
    capture_output: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Langfuse ``@observe`` when configured; identity decorator otherwise."""
    if not is_enabled():

        def passthrough(fn: Callable[P, R]) -> Callable[P, R]:
            return fn

        return passthrough

    from langfuse import observe as langfuse_observe

    return langfuse_observe(
        name=name,
        as_type=as_type,
        capture_input=capture_input,
        capture_output=capture_output,
    )


def openai_client(*, api_key: str, base_url: str):
    """Return an OpenAI client, Langfuse-wrapped when tracing is enabled."""
    if is_enabled():
        from langfuse.openai import OpenAI as LangfuseOpenAI

        return LangfuseOpenAI(api_key=api_key, base_url=base_url)

    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url)


def set_trace_input(value: Any) -> None:
    if not is_enabled():
        return
    from langfuse import get_client

    get_client().update_current_span(input=value)


def set_trace_metadata(**metadata: Any) -> None:
    if not is_enabled():
        return
    from langfuse import get_client

    get_client().update_current_span(metadata=metadata)


def flush() -> None:
    if not is_enabled():
        return
    from langfuse import get_client

    get_client().flush()


if is_enabled():
    atexit.register(flush)
