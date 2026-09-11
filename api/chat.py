"""
HeatLens chat API — Phase 5G.

Exposes POST /api/chat.  Integrated into api/main.py via include_router.

The offline rule (DECISIONS.md D16) is enforced on the frontend: the chat
panel hides itself when /api/health does not answer.  This endpoint itself
makes no guarantees about availability when the LLM backend is unreachable.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Ensure src/ is importable when the API is launched from the project root.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="The user's question in plain English.")
    dataset: str = Field("historical",
                         description="Which dataset to ground answers against: 'historical' or 'live'.")


class ToolTraceItem(BaseModel):
    name: str
    args: dict
    source: str


class ChatResponse(BaseModel):
    answer: str
    tool_trace: list[ToolTraceItem]
    sources: list[str]
    refused: bool
    refusal_reason: str
    guard_passed: bool
    ungrounded_numbers: list[str]
    rounds: int


# ---------------------------------------------------------------------------
# Shared state (injected from main.py)
# ---------------------------------------------------------------------------

# main.py sets this after it imports us, so the chat endpoint can use the
# already-loaded live_cache without re-reading disk.
_live_cache: dict | None = None


def set_live_cache(cache: dict | None) -> None:
    """Called by main.py whenever live_cache is refreshed."""
    global _live_cache
    _live_cache = cache


# Lazy-loaded LLM provider (avoids importing google-generativeai at startup
# if no key is set — the error surfaces only when the endpoint is first hit).
_provider = None


def _get_provider():
    global _provider
    if _provider is None:
        try:
            from heatstress.chat.provider import get_provider
            _provider = get_provider()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Chat agent is unavailable: {exc}. "
                    "Check that GEMINI_API_KEY is set in .env."
                ),
            )
    return _provider


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Run the HeatLens chat agent and return a grounded answer.

    The agent:
    - Refuses questions it cannot honestly answer (headcounts, death tolls).
    - Calls read-only tools to retrieve numeric data.
    - Post-checks that every number in the answer came from a tool return.
    - Returns a full tool trace so the UI can show sources.
    """
    import asyncio

    if req.dataset not in ("historical", "live"):
        raise HTTPException(
            status_code=400,
            detail="dataset must be 'historical' or 'live'.",
        )

    provider = _get_provider()
    payload = _live_cache if req.dataset == "live" else None

    try:
        from heatstress.chat.agent import run_agent
        result = await asyncio.to_thread(
            run_agent,
            question=req.question,
            dataset=req.dataset,
            provider=provider,
            payload=payload,
        )
    except Exception as exc:
        log.exception("Agent error for question %r", req.question)
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    return ChatResponse(
        answer=result.answer,
        tool_trace=[
            ToolTraceItem(name=t.name, args=t.args, source=t.source)
            for t in result.tool_trace
        ],
        sources=result.sources,
        refused=result.refused,
        refusal_reason=result.refusal_reason,
        guard_passed=result.guard_passed,
        ungrounded_numbers=result.ungrounded_numbers,
        rounds=result.rounds,
    )


@router.get("/questions")
def suggested_questions():
    """Return the list of suggested starter questions for the UI."""
    from heatstress.chat.agent import SUGGESTED_QUESTIONS
    return {"questions": SUGGESTED_QUESTIONS}


class WhatIfApiResponse(ChatResponse):
    scenarios: list[dict]
    out_of_scope: bool
    model: str


@router.post("/whatif", response_model=WhatIfApiResponse)
async def whatif(req: ChatRequest):
    """Free-form what-if, answered as a grounded recommendation.

    Same guarantees as /api/chat -- refusal table first, numeric guard last --
    plus a strict project-only scope. ``scenarios`` carries the grid rows the
    answer was built from, so the UI can draw them as before/after cards
    instead of trusting the prose.
    """
    import asyncio

    if req.dataset not in ("historical", "live"):
        raise HTTPException(status_code=400,
                            detail="dataset must be 'historical' or 'live'.")

    provider = _get_provider()
    payload = _live_cache if req.dataset == "live" else None
    try:
        from heatstress.chat.agent import run_whatif_agent
        out = await asyncio.to_thread(
            run_whatif_agent, question=req.question, dataset=req.dataset,
            provider=provider, payload=payload,
        )
    except Exception as exc:
        log.exception("What-if agent error for question %r", req.question)
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    r = out.agent
    return WhatIfApiResponse(
        answer=r.answer,
        tool_trace=[ToolTraceItem(name=t.name, args=t.args, source=t.source)
                    for t in r.tool_trace],
        sources=r.sources,
        refused=r.refused,
        refusal_reason=r.refusal_reason,
        guard_passed=r.guard_passed,
        ungrounded_numbers=r.ungrounded_numbers,
        rounds=r.rounds,
        scenarios=out.scenarios,
        out_of_scope=out.out_of_scope,
        model=getattr(provider, "model_name", "unknown"),
    )


@router.get("/whatif/questions")
def whatif_questions():
    """Starter questions for the decision assistant."""
    from heatstress.chat.agent import WHATIF_SUGGESTED
    return {"questions": WHATIF_SUGGESTED}
