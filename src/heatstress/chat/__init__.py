"""
HeatLens chat package — Phase 5G.

Entry point for the tool-calling agent. Import `build_agent` to get a
ready-to-use agent bound to the configured LLM provider.
"""

from .agent import AgentResponse, run_agent
from .provider import LLMProvider

__all__ = ["run_agent", "AgentResponse", "LLMProvider"]
