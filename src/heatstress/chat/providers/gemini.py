"""
Gemini provider — implements LLMProvider using google-generativeai.

Uses gemini-2.0-flash: fast, cheap, supports parallel function calling.
All Gemini-specific types are translated into the common dataclasses in
provider.py before being returned.  Nothing Gemini-specific escapes this file.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from ..provider import LLMMessage, LLMProvider, LLMResponse, ToolCall

load_dotenv()

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):
    """Google Gemini backend via the google-generativeai SDK."""

    def __init__(self, model: str = _DEFAULT_MODEL):
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model

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
        import google.generativeai as genai
        from google.generativeai.types import content_types

        # Build Gemini tool declarations from JSON-Schema specs.
        gemini_tools = self._build_tools(tools)

        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system or None,
            tools=gemini_tools if gemini_tools else None,
        )

        # Translate our common message format → Gemini content list.
        history, last_user = self._build_history(messages)

        chat_session = model.start_chat(history=history)
        response = chat_session.send_message(last_user)

        return self._parse_response(response)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_tools(self, tools: list[dict]):
        """Convert JSON-Schema tool specs to Gemini FunctionDeclaration list."""
        if not tools:
            return []
        import google.generativeai as genai

        declarations = []
        for spec in tools:
            fn = spec.get("function", spec)   # handle both wrapper and bare
            declarations.append(
                genai.protos.FunctionDeclaration(
                    name=fn["name"],
                    description=fn.get("description", ""),
                    parameters=self._schema_to_gemini(fn.get("parameters", {})),
                )
            )
        return [genai.protos.Tool(function_declarations=declarations)]

    @staticmethod
    def _schema_to_gemini(schema: dict) -> Any:
        """Recursively convert a JSON Schema dict to Gemini Schema proto."""
        import google.generativeai as genai

        type_map = {
            "string": genai.protos.Type.STRING,
            "number": genai.protos.Type.NUMBER,
            "integer": genai.protos.Type.INTEGER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }

        t = schema.get("type", "object")
        gemini_type = type_map.get(t, genai.protos.Type.STRING)

        kwargs: dict[str, Any] = {"type_": gemini_type}

        if "description" in schema:
            kwargs["description"] = schema["description"]

        if t == "object" and "properties" in schema:
            props = {}
            for name, prop_schema in schema["properties"].items():
                props[name] = GeminiProvider._schema_to_gemini(prop_schema)
            kwargs["properties"] = props
            if "required" in schema:
                kwargs["required"] = schema["required"]

        if t == "array" and "items" in schema:
            kwargs["items"] = GeminiProvider._schema_to_gemini(schema["items"])

        if "enum" in schema:
            kwargs["enum"] = schema["enum"]

        return genai.protos.Schema(**kwargs)

    def _build_history(self, messages: list[LLMMessage]):
        """Split messages into Gemini history (all but last user) + last message.

        Gemini's chat history must alternate user/model.  Tool results are
        encoded as function_response parts on a "user" turn following the
        model's function_call turn.
        """
        import google.generativeai as genai

        gemini_contents = []

        for msg in messages:
            if msg.role == "user" and msg.content:
                gemini_contents.append(
                    {"role": "user", "parts": [{"text": msg.content}]}
                )
            elif msg.role == "assistant":
                parts = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tc in msg.tool_calls:
                    parts.append({
                        "function_call": {
                            "name": tc.name,
                            "args": tc.args,
                        }
                    })
                if parts:
                    gemini_contents.append({"role": "model", "parts": parts})
            elif msg.role == "tool" and msg.tool_name:
                result = msg.tool_result
                if not isinstance(result, dict):
                    result = {"result": result}
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"function_response": {
                        "name": msg.tool_name,
                        "response": result,
                    }}],
                })

        if not gemini_contents:
            raise ValueError("No messages to send.")

        last = gemini_contents[-1]
        history = gemini_contents[:-1]
        return history, last["parts"]

    def _parse_response(self, response) -> LLMResponse:
        """Translate a Gemini response into our common LLMResponse."""
        text_parts = []
        tool_calls = []

        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                # Gemini returns a MapComposite; cast to plain dict.
                args = dict(fc.args) if fc.args else {}
                tool_calls.append(ToolCall(name=fc.name, args=args))

        stop_reason = "end_turn"
        if tool_calls:
            stop_reason = "tool_use"
        elif candidate.finish_reason and candidate.finish_reason.name == "MAX_TOKENS":
            stop_reason = "max_tokens"

        return LLMResponse(
            text="\n".join(text_parts) or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
        )
