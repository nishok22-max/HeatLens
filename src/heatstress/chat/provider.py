"""
Provider-agnostic LLM interface for the HeatLens chat agent.

The agent, tools, guards, and API contract are all written against the
abstract ``LLMProvider`` class and the two dataclasses below.  Nothing
from Gemini or Groq's SDK leaks past the ``providers/`` layer, so swapping
backends requires only a new file in ``providers/`` and a one-line change
in ``get_provider()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMessage:
    """One turn in the conversation history."""
    role: str          # "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # When role=="tool", the result of executing a tool call.
    tool_name: str | None = None
    tool_result: Any = None
    raw_parts: Any = None


@dataclass
class LLMResponse:
    """What the provider returns for one generate call."""
    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: str   # "tool_use" | "end_turn" | "max_tokens"
    raw_parts: Any = None


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract LLM backend.

    Implementors must translate their SDK's types into the common dataclasses
    above.  The agent loop never touches provider-specific objects.
    """

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict],          # JSON-Schema tool descriptions
        system: str = "",
    ) -> LLMResponse:
        """Send a conversation turn and return the model's response.

        Args:
            messages:  Full conversation history so far.
            tools:     List of tool specs in OpenAI/Gemini function-calling
                       JSON-Schema format.
            system:    System prompt to prepend (if the provider supports it).
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier for logging and the tool trace."""


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def get_provider(provider_name: str | None = None) -> LLMProvider:
    """Return the configured LLM provider.

    Resolution order:
      1. ``provider_name`` argument
      2. ``LLM_PROVIDER`` environment variable
      3. Default: ``gemini``
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()

    name = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).lower()

    if name == "gemini":
        from .providers.gemini import GeminiProvider
        return GeminiProvider()
    if name == "groq":
        from .providers.groq import GroqProvider
        return GroqProvider()

    raise ValueError(
        f"Unknown LLM provider {name!r}. "
        f"Set LLM_PROVIDER to 'gemini' or 'groq'."
    )
