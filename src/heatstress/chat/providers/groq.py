"""
Groq provider stub — not yet implemented.

Wire this up by:
  1. pip install groq
  2. Add GROQ_API_KEY to .env
  3. Implement chat() using groq.Groq client with tool_choice support
  4. Change LLM_PROVIDER=groq in .env
"""

from __future__ import annotations

from ..provider import LLMMessage, LLMProvider, LLMResponse


class GroqProvider(LLMProvider):
    """Groq backend — stub, raises NotImplementedError."""

    @property
    def model_name(self) -> str:
        return "groq/llama-3.3-70b-versatile"  # intended target model

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        raise NotImplementedError(
            "Groq provider is not yet implemented. "
            "Set LLM_PROVIDER=gemini in .env to use the Gemini backend."
        )
