"""Unit tests for llm.complete multi-round handling."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from openai import RateLimitError

from stock_radar.llm.llm import (
    MAX_COMPLETION_ROUNDS,
    REASONING_CONTINUATION_PROMPT,
    TRUNCATION_CONTINUATION_PROMPT,
    _extract_content,
    _should_continue_reasoning,
    _try_extract_content,
    complete,
)


def _message(*, content: str | None = None, reasoning: str | None = None):
    extra = {"reasoning_content": reasoning} if reasoning else {}
    return SimpleNamespace(content=content, model_extra=extra, tool_calls=None)


def _response(message, *, finish_reason: str = "stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


class ExtractContentTests(unittest.TestCase):
    def test_prefers_content_over_reasoning(self):
        msg = _message(content="final", reasoning="thinking")
        self.assertEqual(_try_extract_content(msg), "final")

    def test_reasoning_only_returns_none(self):
        msg = _message(content=None, reasoning="thinking")
        self.assertIsNone(_try_extract_content(msg))
        self.assertTrue(_should_continue_reasoning(msg))

    def test_empty_raises(self):
        with self.assertRaisesRegex(RuntimeError, "empty content"):
            _extract_content(_message())


class CompleteTests(unittest.TestCase):
    @patch("stock_radar.llm.llm.get_client")
    def test_passes_reasoning_effort_low(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.return_value = _response(_message(content="digest"))

        complete("prompt", model="deepseek-v4-flash", max_tokens=100, reasoning_effort="low")

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["reasoning_effort"], "low")
        self.assertEqual(kwargs["name"], "deepseek-generation-1-initial")
        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled"}})

    @patch("stock_radar.llm.llm.get_client")
    def test_returns_content_on_first_round(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.return_value = _response(_message(content="digest"))

        result = complete("prompt", model="deepseek-v4-flash", max_tokens=100)

        self.assertEqual(result, "digest")
        client.chat.completions.create.assert_called_once()

    @patch("stock_radar.llm.llm.get_client")
    def test_retries_when_only_reasoning_then_content(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.side_effect = [
            _response(_message(reasoning="step 1")),
            _response(_message(content="digest")),
        ]

        result = complete("prompt", model="deepseek-v4-flash", max_tokens=100)

        self.assertEqual(result, "digest")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        second_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
        self.assertEqual(len(second_messages), 3)
        self.assertEqual(second_messages[2]["content"], REASONING_CONTINUATION_PROMPT)

    @patch("stock_radar.llm.llm.get_client")
    def test_raises_after_max_rounds_of_reasoning_only(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.return_value = _response(
            _message(reasoning="still thinking")
        )

        with self.assertRaisesRegex(RuntimeError, f"{MAX_COMPLETION_ROUNDS} round"):
            complete("prompt", model="deepseek-v4-flash", max_tokens=100)

        self.assertEqual(client.chat.completions.create.call_count, MAX_COMPLETION_ROUNDS)

    @patch("stock_radar.llm.llm.get_client")
    def test_continues_when_finish_reason_length(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.side_effect = [
            _response(_message(content="part one"), finish_reason="length"),
            _response(_message(content="part two"), finish_reason="stop"),
        ]

        result = complete("prompt", model="deepseek-v4-flash", max_tokens=100)

        self.assertEqual(result, "part onepart two")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        second_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
        self.assertEqual(second_messages[2]["content"], TRUNCATION_CONTINUATION_PROMPT)

    @patch("stock_radar.llm.llm.get_client")
    def test_continues_when_is_complete_reports_missing_sections(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.side_effect = [
            _response(_message(content="partial")),
            _response(_message(content="##done")),
        ]

        result = complete(
            "prompt",
            model="deepseek-v4-flash",
            max_tokens=100,
            is_complete=lambda md: md.endswith("##done"),
        )

        self.assertEqual(result, "partial##done")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    @patch("stock_radar.llm.llm.time.sleep")
    @patch("stock_radar.llm.llm.get_client")
    def test_retries_transient_api_errors(self, get_client, _sleep):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.side_effect = [
            RateLimitError("rate limited", response=MagicMock(), body=None),
            _response(_message(content="digest")),
        ]

        result = complete("prompt", model="deepseek-v4-flash", max_tokens=100)

        self.assertEqual(result, "digest")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    @patch("stock_radar.llm.llm.get_client")
    def test_disables_thinking_when_requested(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.chat.completions.create.return_value = _response(_message(content="digest"))

        complete("prompt", model="deepseek-v4-flash", max_tokens=100, thinking=False)

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "disabled"}})


if __name__ == "__main__":
    unittest.main()
