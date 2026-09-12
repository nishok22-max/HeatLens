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
city-level heat-stress analysis for Ahmedabad. You are also a knowledgeable
heat-health advisor who can answer general physiology and first-aid questions.

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
7. When asked about population exposure, vulnerable demographics, or people at risk,
   call get_population_exposure. Cite the exact measured demographic figures (elderly 60+,
   children under 6, tin/asbestos roof dwellers, outdoor laborers) and top wards.
   Clarify that mortality / casualty counts are not provided because mortality models
   are not calibrated to hospital records.

GENERAL HEALTH KNOWLEDGE (when no tool covers the topic):
- If the user asks a general physiology, first-aid, or public-health question
  that the HeatLens data tools do not cover (e.g. "what happens if I drink
  cold water vs normal water in extreme heat?"), you MUST answer using your
  general medical and physiological training knowledge. Do NOT refuse or say
  the model cannot estimate it — just answer the health question directly.
- You MUST clearly prefix such sections with:
    ⚕️ General Health Advice (not from HeatLens data):
- Still anchor the response to the current heat context where possible:
  call get_city_summary or get_advisory first to fetch the zone UTCI/WBGT,
  then weave that context into your health explanation.
- Do not invent any numbers; if you cite a temperature figure it must come
  from a tool return. Qualitative physiological descriptions (e.g. "cold
  water causes rapid vasoconstriction") are fine without a tool source.
- Keep it actionable and practical — health workers and citizens need clear
  advice, not academic hedging.

STYLE:
- Use °C for temperatures.
- Name the tool you used (e.g. "According to the work-safety window…").
- If a caveat in the data is directly relevant, surface it.
""".strip()

SUGGESTED_QUESTIONS = [
    "What is the peak UTCI today and which zone is hottest?",
    "How many people and vulnerable residents are exposed to extreme heat?",
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
    system_core: str | None = None,
    tools: list[dict] | None = None,
) -> AgentResponse:
    """Run the full chat agent and return a grounded response.

    Args:
        question: The user's question in plain English.
        dataset:  'historical' | 'live' — which baked payload to load.
        provider: LLM backend.  Defaults to whatever get_provider() returns.
        payload:  Pre-loaded live_cache dict (avoids re-reading disk in the API).
        system_core: Replaces the default system prompt (the what-if agent
                  uses a stricter, decision-focused one). Guards still apply.
        tools:    Restricts which tools the model may call. Defaults to all.
    """
    tool_specs = TOOL_SPECS if tools is None else tools
    # --- lazy provider ---
    if provider is None:
        from .provider import get_provider
        provider = get_provider()

    live = dataset == "live"

    # 1. Refusal check (before any LLM call — saves tokens and is guaranteed).
    from pathlib import Path
    # Population, not vulnerability: the headcount refusal is lifted only when a
    # measured population layer exists (scripts/14_population.py -> WorldPop).
    # Vulnerability stays a placeholder either way, so questions about WHO is
    # vulnerable are still answered by the tool's own _not_available field.
    pop_path = (Path(__file__).resolve().parents[3]
                / "data" / "processed" / "population_ahmedabad.json")
    has_pop = pop_path.exists()
    refusal_table = RefusalTable(has_population_data=has_pop)
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
    system = system_core or _SYSTEM_CORE
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
            tools=tool_specs,
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
                raw_parts=response.raw_parts,
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


# ---------------------------------------------------------------------------
# What-if decision agent
#
# Same loop, same guards (refusal table first, numeric guard last), but a
# narrower job: turn any wording of a heat-response question into the levers
# the physics models, compare them, and recommend. Scope is enforced twice --
# the prompt asks for a sentinel on off-topic questions, and the sentinel is
# swapped for a fixed reply here, so no off-topic prose ever reaches the UI.
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_TOKEN = "[[OUT_OF_SCOPE]]"

OUT_OF_SCOPE_REPLY = (
    "I can only help with heat-stress decisions for this city using HeatLens "
    "data. Try something like \"Should we shade work sites or move shifts "
    "earlier for construction workers?\" or \"Which neighbourhoods need relief "
    "first, and what would help most?\""
)

WHATIF_TOOL_NAMES = (
    "simulate_intervention", "list_intervention_options", "get_hottest_zones",
    "get_insights", "get_work_safety_window", "get_city_summary",
    "get_exposure_response", "get_metadata",
)

WHATIF_SUGGESTED = [
    "We can afford only one measure this week. What protects construction workers most?",
    "Is tarpaulin over work sites better than planting trees?",
    "Delivery riders start at 9. What if they started at dawn instead?",
    "Which neighbourhoods should get relief first, and what would help there?",
    "Combine the best shade and the best shift. How much safer is that?",
]

_WHATIF_SYSTEM = f"""
You are the HeatLens Decision Assistant. You help municipal officials, health
officers and labour inspectors decide what to do about heat stress in the city
covered by the HeatLens data, using ONLY that model.

SCOPE (strict):
- Answer only questions about heat stress, heatwave preparedness and response,
  outdoor-work safety, public-health advisories, and the interventions HeatLens
  models, for this city.
- If the question is about anything else (general knowledge, coding, sport,
  politics, other cities, personal matters), reply with exactly
  {OUT_OF_SCOPE_TOKEN} and nothing else.

HOW TO ANSWER:
1. Always call tools before answering. For any what-if, comparison or "what
   should we do" question, call simulate_intervention once per option, or
   list_intervention_options to compare everything. For "where", call
   get_hottest_zones.
2. Map loose wording onto the modelled levers: tarps, canopies, covering sites
   -> shade_pct; trees, parks, green roofs -> greening_pct; start earlier,
   dawn shifts, split shift -> shift_start_hour; riders -> delivery;
   labourers, builders -> construction; school -> child; old people -> elderly.
   If no amount is given, compare a low and a high value.
3. If the question asks about something HeatLens does not model (cooling
   centres, water stations, air conditioning, power grid, hospital beds), say
   so plainly, offer the closest modelled lever if it helps, and put any
   general advice under "Not modelled by HeatLens:" with no numbers.
4. Every number must come from a tool return. Never estimate, interpolate or
   invent a figure. If a value was snapped to the grid, say so.
5. Never give death or hospital-admission counts: risk is relative. Never say
   "validated".

FORMAT (markdown, short, for a busy official):
**Recommendation:** one or two sentences stating the decision.
**Evidence:** 2-4 bullets, each a modelled before -> after figure.
**Trade-offs:** 1-3 bullets on cost and feasibility, from the tool data.
**Limits:** one line on what this does not cover, only if relevant.
""".strip()


@dataclass
class WhatIfAgentResponse:
    agent: AgentResponse
    scenarios: list[dict] = field(default_factory=list)
    out_of_scope: bool = False


def run_whatif_agent(
    question: str,
    dataset: str = "historical",
    provider: LLMProvider | None = None,
    payload: dict | None = None,
) -> WhatIfAgentResponse:
    """Answer a free-form what-if as a grounded, decision-focused recommendation."""
    tools = [s for s in TOOL_SPECS if s["function"]["name"] in WHATIF_TOOL_NAMES]
    result = run_agent(question, dataset=dataset, provider=provider,
                       payload=payload, system_core=_WHATIF_SYSTEM, tools=tools)

    if OUT_OF_SCOPE_TOKEN in (result.answer or ""):
        result.answer = OUT_OF_SCOPE_REPLY
        result.refused = True
        result.refusal_reason = "out_of_scope"
        result.guard_passed = True
        result.ungrounded_numbers = []
        return WhatIfAgentResponse(agent=result, out_of_scope=True)

    scenarios = [
        {k: v for k, v in t.result.items() if not k.startswith("_")}
        for t in result.tool_trace
        if t.name == "simulate_intervention"
        and isinstance(t.result, dict) and "error" not in t.result
    ]
    return WhatIfAgentResponse(agent=result, scenarios=scenarios)


def _last_text(messages: list[LLMMessage]) -> str:
    """Return the last assistant text in the conversation."""
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.content:
            return msg.content
    return ""
