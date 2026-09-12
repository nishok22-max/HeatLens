"""
Groq provider — implements LLMProvider using the Groq SDK.

Groq speaks the OpenAI chat-completions dialect, which differs from the
common dataclasses in two ways that matter:

  1. Tool arguments arrive as a JSON *string*, not a dict.
  2. Every tool result must name the ``tool_call_id`` it answers.

The second is the awkward one, because ``LLMMessage(role="tool", ...)``
carries no id -- the agent loop was written against Gemini, where a tool
result is matched by function *name*. The ids are therefore stashed on the
assistant turn's ``raw_parts`` (which the loop already round-trips
verbatim) and paired back positionally: the loop executes tool calls in
order and appends their results in the same order, so the nth tool message
after an assistant turn answers that turn's nth tool call.

Nothing Groq-specific escapes this file.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from ..provider import LLMMessage, LLMProvider, LLMResponse, ToolCall

load_dotenv()

# Tool-capable, and the whole reason for this backend: a two-round agent
# question measured 1.6 s here against 177 s on the previous model. Groq no
# longer serves llama-3.3-70b-versatile, which this file's stub named as the
# intended target. Override with GROQ_MODEL.
_DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqProvider(LLMProvider):
    """Groq backend via the official SDK."""

    def __init__(self, model: str | None = None):
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )
        self._client = Groq(api_key=api_key)
        self._model_name = model or os.getenv("GROQ_MODEL", _DEFAULT_MODEL)

    @property
    def model_name(self) -> str:
        return self._model_name

    # ------------------------------------------------------------------
    # Main interface
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        payload = self._build_messages(messages, system)

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": payload,
            # The agent is a retrieval loop, not a writer: keep it literal.
            "temperature": 0.2,
        }
        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tools(tools: list[dict]) -> list[dict]:
        """Normalise tool specs to OpenAI's ``{"type": "function", ...}`` shape.

        The agent hands over either the bare function spec or one already
        wrapped, so accept both rather than depending on which.
        """
        out = []
        for spec in tools:
            fn = spec.get("function", spec)
            out.append({
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return out

    def _build_messages(self, messages: list[LLMMessage], system: str) -> list[dict]:
        """Translate the common message list into Groq's chat format."""
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})

        # Ids from the most recent assistant turn, consumed in order by the
        # tool messages that follow it. See the module docstring.
        pending_ids: list[str] = []

        for msg in messages:
            if msg.role == "user":
                out.append({"role": "user", "content": msg.content or ""})

            elif msg.role == "assistant":
                if not msg.tool_calls:
                    out.append({"role": "assistant", "content": msg.content or ""})
                    pending_ids = []
                    continue

                # raw_parts holds the ids this provider minted last round; if
                # the turn came from somewhere else, synthesise stable ones.
                ids = list(msg.raw_parts or [])
                if len(ids) != len(msg.tool_calls):
                    ids = [f"call_{i}" for i in range(len(msg.tool_calls))]

                out.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.args or {}),
                            },
                        }
                        for call_id, tc in zip(ids, msg.tool_calls)
                    ],
                })
                pending_ids = ids

            elif msg.role == "tool" and msg.tool_name:
                call_id = pending_ids.pop(0) if pending_ids else f"call_{msg.tool_name}"
                result = msg.tool_result
                out.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": msg.tool_name,
                    "content": json.dumps(result, default=str),
                })

        if not out or all(m["role"] == "system" for m in out):
            raise ValueError("No messages to send.")
        return out

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Translate a Groq completion into the common LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        ids: list[str] = []
        for tc in message.tool_calls or []:
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                # A model that emits malformed JSON has not really called the
                # tool. Passing {} on runs it with silent defaults, so keep the
                # empty args visible rather than inventing plausible ones.
                args = {}
            if not isinstance(args, dict):
                args = {"value": args}
            tool_calls.append(ToolCall(name=tc.function.name, args=args))
            ids.append(tc.id)

        if tool_calls:
            stop_reason = "tool_use"
        elif choice.finish_reason == "length":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"

        return LLMResponse(
            text=message.content or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            # Carries the ids forward so the next round can pair tool results.
            raw_parts=ids,
        )
