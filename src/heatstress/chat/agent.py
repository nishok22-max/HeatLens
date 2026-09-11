"""
Agentic orchestration loop for the HeatLens chat agent (Phase 5G).

DESIGN INVARIANT: The LLM selects tools and writes prose.  It never supplies
a numeric figure that did not originate from a tool return.

Loop:
  1. Check refusal table — return early if applicable.
  2. Retrieve relevant passages (retriever.py).
  3. Build system prompt embedding retrieved context + rules.
  4. Agentic loop (max MAX_ROUNDS):
       LLM response → if tool_calls: execute → feed results → next round
  5. Collect all tool_returns.
  6. Numeric guard post-check on final answer text.
  7. If guard fails: append a correction instruction and re-generate once.
  8. Return AgentResponse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .guards import NumericGuard, RefusalTable
from .provider import LLMMessage, LLMProvider, ToolCall
from .retriever import get_retriever
from .tools import TOOL_SPECS, execute_tool

log = logging.getLogger(__name__)

MAX_ROUNDS = 6   # hard cap on LLM call count per question

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_CORE = """
You are the HeatLens data assistant — a concise, precise guide to the
city-level heat-stress analysis for Ahmedabad.

CORE RULES (non-negotiable):
1. Every number in your answer must come from a tool return.
   Never invent or recall a figure from training data.
2. When asked for advisory text, reproduce it verbatim from the tool.
   Do not paraphrase public-health instructions.
3. Refer to heat risk as "relative" unless the exposure-response tool
   reports is_calibrated=True.
4. Never use the bare word "validated" — say "cross-checked against
   held-out satellite observations" when that is what you mean.
5. If a tool returns an error, say so clearly and offer an alternative.
6. Be concise. Municipal officers and health workers need facts, not essays.

STYLE:
- Use °C for temperatures.
- Name the tool you used (e.g. "According to the work-safety window…").
- If a caveat in the data is directly relevant, surface it.
""".strip()

SUGGESTED_QUESTIONS = [
    "What is the peak UTCI today and which zone is hottest?",
    "When is it safe for construction workers to be outside?",
    "What is driving the heat stress — temperature, humidity, or sun?",
    "What would happen if we greened the hottest neighbourhoods?",
    "What does the public advisory say right now?",
    "Why does UTCI show a bigger spread than WBGT?",
    "What are the key limitations of this model?",
]


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------

@dataclass
class ToolTrace:
    """Record of one tool call and its return."""
    name: str
    args: dict
    result: Any
    source: str = ""


@dataclass
class AgentResponse:
    answer: str
    tool_trace: list[ToolTrace] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    retrieved_passages: list[str] = field(default_factory=list)
    refused: bool = False
    refusal_reason: str = ""
    guard_passed: bool = True
    ungrounded_numbers: list[str] = field(default_factory=list)
    rounds: int = 0


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def run_agent(
    question: str,
    dataset: str = "historical",
    provider: LLMProvider | None = None,
    payload: dict | None = None,
) -> AgentResponse:
    """Run the full chat agent and return a grounded response.

    Args:
        question: The user's question in plain English.
        dataset:  'historical' | 'live' — which baked payload to load.
        provider: LLM backend.  Defaults to whatever get_provider() returns.
        payload:  Pre-loaded live_cache dict (avoids re-reading disk in the API).
    """
    # --- lazy provider ---
    if provider is None:
        from .provider import get_provider
        provider = get_provider()

    live = dataset == "live"

    # 1. Refusal check (before any LLM call — saves tokens and is guaranteed).
    refusal_table = RefusalTable()
    refusal = refusal_table.check(question)
    if refusal:
        return AgentResponse(
            answer=refusal.response,
            refused=True,
            refusal_reason=refusal.reason,
            guard_passed=True,  # refusals are always grounded
        )

    # 2. Retrieve relevant passages.
    try:
        retriever = get_retriever()
        passages = retriever.retrieve(question, k=4)
        retrieved_texts = [p.text for p in passages]
        context_block = "\n\n---\n\n".join(
            f"[{p.source}]\n{p.text}" for p in passages
        )
    except Exception as exc:
        log.warning("Retriever failed: %s", exc)
        retrieved_texts = []
        context_block = ""

    # 3. Build system prompt.
    system = _SYSTEM_CORE
    if context_block:
        system += (
            "\n\nRELEVANT BACKGROUND (from project documents):\n"
            + context_block
        )

    # 4. Agentic loop.
    messages: list[LLMMessage] = [
        LLMMessage(role="user", content=question)
    ]
    all_tool_returns: list[dict] = []
    tool_trace: list[ToolTrace] = []
    rounds = 0

    while rounds < MAX_ROUNDS:
        rounds += 1
        response = provider.chat(
            messages=messages,
            tools=TOOL_SPECS,
            system=system,
        )

        if response.stop_reason == "end_turn" or not response.tool_calls:
            # Final answer — append text and break.
            if response.text:
                messages.append(
                    LLMMessage(role="assistant", content=response.text)
                )
            break

        # Execute tool calls.
        messages.append(
            LLMMessage(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
            )
        )

        for tc in response.tool_calls:
            result = execute_tool(tc.name, tc.args, payload=payload, live=live)
            all_tool_returns.append(result)
            tool_trace.append(ToolTrace(
                name=tc.name,
                args=tc.args,
                result=result,
                source=result.get("_source", ""),
            ))
            messages.append(
                LLMMessage(
                    role="tool",
                    tool_name=tc.name,
                    tool_result=result,
                )
            )

    # 5. Extract final answer text.
    final_text = _last_text(messages)
    if not final_text:
        final_text = (
            "I was unable to produce an answer. "
            "Please try rephrasing your question."
        )

    # 6. Numeric guard post-check.
    guard = NumericGuard()
    guard_result = guard.check(final_text, all_tool_returns, question=question)

    if not guard_result.passed:
        log.warning("Numeric guard failed: %s", guard_result.message)
        # One correction round.
        correction_msg = (
            f"Your previous answer contained numbers ({guard_result.ungrounded}) "
            f"that were not in any tool return. "
            f"Please rewrite your answer using ONLY figures from the tool results "
            f"already in this conversation. Do not introduce any new numbers."
        )
        messages.append(LLMMessage(role="user", content=correction_msg))
        try:
            correction = provider.chat(messages=messages, tools=[], system=system)
            if correction.text:
                final_text = correction.text
                rounds += 1
        except Exception as exc:
            log.error("Correction round failed: %s", exc)

        guard_result2 = guard.check(final_text, all_tool_returns, question=question)
        guard_passed = guard_result2.passed
        ungrounded = guard_result2.ungrounded
    else:
        guard_passed = True
        ungrounded = []

    sources = sorted({t.source for t in tool_trace if t.source})

    return AgentResponse(
        answer=final_text,
        tool_trace=tool_trace,
        sources=sources,
        retrieved_passages=retrieved_texts,
        refused=False,
        guard_passed=guard_passed,
        ungrounded_numbers=ungrounded,
        rounds=rounds,
    )


def _last_text(messages: list[LLMMessage]) -> str:
    """Return the last assistant text in the conversation."""
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.content:
            return msg.content
    return ""
