"""Tests for the what-if decision assistant: its tools, its scope, its guards.

No network and no API key: the LLM is replaced by a scripted provider that
returns fixed responses, so these tests check what the code does with a
model's output -- tool dispatch, scenario extraction, the numeric guard, the
out-of-scope swap -- not how clever the model is.
"""

import json
from pathlib import Path

import pytest

from heatstress.chat import agent as ag
from heatstress.chat.provider import LLMProvider, LLMResponse, ToolCall
from heatstress.chat.tools import TOOL_SPECS, execute_tool

ROOT = Path(__file__).resolve().parents[1]
GRID = json.loads((ROOT / "web" / "data" / "insights.json")
                  .read_text(encoding="utf-8"))["scenario_grid"]
AXES = GRID["axes"]


class Scripted(LLMProvider):
    """Returns the queued responses in order and records what it was sent."""

    def __init__(self, responses):
        self._queue = list(responses)
        self.calls = []

    def chat(self, messages, tools, system=""):
        self.calls.append({"tools": [t["function"]["name"] for t in tools],
                           "system": system})
        return self._queue.pop(0)

    @property
    def model_name(self):
        return "scripted"


@pytest.fixture(autouse=True)
def no_retriever(monkeypatch):
    """The retriever loads an embedding model; the agent tolerates its absence."""
    def unavailable():
        raise RuntimeError("retriever disabled in tests")
    monkeypatch.setattr(ag, "get_retriever", unavailable)


def tool_turn(name, **args):
    return LLMResponse(text=None, tool_calls=[ToolCall(name=name, args=args)],
                       stop_reason="tool_use")


def final(text):
    return LLMResponse(text=text, tool_calls=[], stop_reason="end_turn")


def simulate(**args):
    return execute_tool("simulate_intervention", args)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TestSimulateIntervention:
    def test_every_shade_grid_value_is_found_without_a_snap(self):
        for shade in AXES["shade"]:
            out = simulate(shade_pct=round(shade * 100))
            assert out["cooling"]["shade"] == shade
            assert out["snaps"] == []

    def test_an_off_grid_value_snaps_and_says_so(self):
        values = sorted(AXES["shade"])
        between = (values[0] + values[1]) / 2 * 100 + 1  # just past the midpoint
        out = simulate(shade_pct=between)
        assert out["cooling"]["shade"] in values
        assert out["snaps"] and out["snaps"][0]["parameter"] == "shade"

    def test_the_row_matches_the_grid_exactly(self):
        shade, greening = AXES["shade"][-1], AXES["greening"][-1]
        row = next(r for r in GRID["cooling"]
                   if r["shade"] == shade and r["greening"] == greening)
        out = simulate(shade_pct=round(shade * 100), greening_pct=round(greening * 100))
        assert out["cooling"]["utci_after"] == row["utci_after"]
        assert out["cooling"]["delta_c"] == row["delta_c"]

    def test_shift_defaults_to_the_first_persona(self):
        hour = AXES["shift_start"][0]
        out = simulate(shift_start_hour=hour)
        assert out["scheduling"]["shift_start"] == hour
        assert out["scheduling"]["persona"] == AXES["persona"][0]

    def test_rejects_no_lever_bad_range_and_unknown_persona(self):
        assert "error" in simulate()
        assert "error" in simulate(shade_pct=150)
        assert "error" in simulate(shift_start_hour=AXES["shift_start"][0], persona="astronaut")


class TestComparisonTools:
    def test_options_cover_the_whole_grid_ranked(self):
        out = execute_tool("list_intervention_options", {})
        cooling = out["cooling_ranked_most_cooling_first"]
        assert len(cooling) == len(GRID["cooling"])
        assert [r["delta_c"] for r in cooling] == sorted(r["delta_c"] for r in cooling)
        assert len(out["scheduling_ranked_biggest_reduction_first"]) == len(GRID["scheduling"])
        assert out["not_modelled"], "what is not modelled must travel with the options"

    def test_hottest_zones_are_distinct_places_in_order(self):
        out = execute_tool("get_hottest_zones", {"n": 5})
        zones = out["zones"]
        assert len(zones) == 5
        assert len({z["hex_id"] for z in zones}) == 5
        utci = [z["utci_c"] for z in zones]
        assert utci == sorted(utci, reverse=True)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class TestWhatIfAgent:
    def test_grounded_answer_surfaces_its_scenario(self):
        shade = round(AXES["shade"][-1] * 100)
        row = simulate(shade_pct=shade)["cooling"]
        provider = Scripted([
            tool_turn("simulate_intervention", shade_pct=shade),
            final(f"**Recommendation:** shade work sites. Felt heat falls to "
                  f"{row['utci_after']} °C."),
        ])
        out = ag.run_whatif_agent("tarps over sites?", provider=provider)
        assert not out.out_of_scope
        assert out.agent.guard_passed
        assert len(out.scenarios) == 1
        assert out.scenarios[0]["cooling"]["utci_after"] == row["utci_after"]
        assert not any(k.startswith("_") for k in out.scenarios[0])

    def test_only_decision_tools_and_the_decision_prompt_are_offered(self):
        provider = Scripted([final("ok")])
        ag.run_whatif_agent("what should we do?", provider=provider)
        offered = set(provider.calls[0]["tools"])
        assert offered == set(ag.WHATIF_TOOL_NAMES)
        assert offered <= {s["function"]["name"] for s in TOOL_SPECS}
        assert "Decision Assistant" in provider.calls[0]["system"]
        assert ag.OUT_OF_SCOPE_TOKEN in provider.calls[0]["system"]

    def test_off_topic_is_swapped_for_the_fixed_reply(self):
        provider = Scripted([final(ag.OUT_OF_SCOPE_TOKEN)])
        out = ag.run_whatif_agent("who won the cricket?", provider=provider)
        assert out.out_of_scope and out.agent.refused
        assert out.agent.answer == ag.OUT_OF_SCOPE_REPLY
        assert out.scenarios == []

    def test_an_invented_number_triggers_one_grounded_rewrite(self):
        shade = round(AXES["shade"][-1] * 100)
        row = simulate(shade_pct=shade)["cooling"]
        provider = Scripted([
            tool_turn("simulate_intervention", shade_pct=shade),
            final("Shade saves 77.77 °C."),                      # invented
            final(f"Shade brings felt heat to {row['utci_after']} °C."),
        ])
        out = ag.run_whatif_agent("is shade worth it?", provider=provider)
        assert out.agent.guard_passed
        assert "77.77" not in out.agent.answer
        assert provider.calls[-1]["tools"] == [], "the rewrite may not call tools"

    def test_death_counts_are_refused_before_any_model_call(self):
        provider = Scripted([])
        out = ag.run_whatif_agent("how many will die if we add shade?", provider=provider)
        assert out.agent.refused and provider.calls == []


class TestChatAgentScope:
    """The general chat agent's scope boundary.

    It was missing: the prompt told the model to answer from training
    knowledge whenever no tool covered the topic, with no domain limit, so
    "what is c-programming?" came back as a full essay on Dennis Ritchie.
    The what-if agent had this guard from the start; these tests hold the
    general agent to the same contract.
    """

    def test_the_prompt_carries_the_sentinel_and_the_boundary(self):
        provider = Scripted([final("ok")])
        ag.run_agent("how hot is it?", provider=provider)
        system = provider.calls[0]["system"]
        assert ag.OUT_OF_SCOPE_TOKEN in system
        assert "SCOPE (strict)" in system

    def test_off_topic_is_swapped_for_the_fixed_reply(self):
        provider = Scripted([final(ag.OUT_OF_SCOPE_TOKEN)])
        result = ag.run_agent("what is c-programming?", provider=provider)
        assert result.refused
        assert result.refusal_reason == "out_of_scope"
        assert result.answer == ag.CHAT_OUT_OF_SCOPE_REPLY
        # A refusal states no figures, so it is grounded by construction.
        assert result.guard_passed

    def test_the_sentinel_wins_even_when_wrapped_in_prose(self):
        # A model that pads the sentinel must not leak the padding either.
        provider = Scripted([final(f"Sure! {ag.OUT_OF_SCOPE_TOKEN}")])
        result = ag.run_agent("write me a python function", provider=provider)
        assert result.answer == ag.CHAT_OUT_OF_SCOPE_REPLY
        assert "Sure!" not in result.answer

    def test_heat_health_questions_are_still_answered(self):
        # The general-health capability is deliberate; the boundary must not
        # take it with it. Nothing off-topic here, so no sentinel is emitted.
        answer = "General Health Advice: drink water steadily rather than in gulps."
        provider = Scripted([final(answer)])
        result = ag.run_agent("should I drink cold water in extreme heat?",
                              provider=provider)
        assert not result.refused
        assert result.answer == answer
