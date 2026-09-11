"""Tests for measured population exposure tool and chat agent integration.

Verifies:
1. get_population_exposure returns measured demographic figures from Census 2011 + GHS-POP.
2. The chat agent answers population exposure / people-at-risk queries with real figures.
3. Death/casualty predictions remain strictly refused (uncalibrated mortality invariant).
4. NumericGuard validates that all numbers cited in the agent's answer originate from the tool.
"""

from pathlib import Path
import pytest

from heatstress.chat import agent as ag
from heatstress.chat.guards import RefusalTable, NumericGuard
from heatstress.chat.provider import LLMProvider, LLMResponse, ToolCall
from heatstress.chat.tools import TOOL_SPECS, execute_tool

ROOT = Path(__file__).resolve().parents[1]


class ScriptedProvider(LLMProvider):
    def __init__(self, responses):
        self._queue = list(responses)
        self.calls = []

    def chat(self, messages, tools, system=""):
        self.calls.append({
            "tools": [t["function"]["name"] for t in tools] if tools else [],
            "messages": messages,
            "system": system,
        })
        return self._queue.pop(0)

    @property
    def model_name(self):
        return "scripted-test"


@pytest.fixture(autouse=True)
def no_retriever(monkeypatch):
    """Disable retriever in unit test."""
    def unavailable():
        raise RuntimeError("retriever disabled in tests")
    monkeypatch.setattr(ag, "get_retriever", unavailable)


class TestPopulationExposureTool:
    def test_tool_returns_measured_demographics(self):
        res = execute_tool("get_population_exposure", {"top_n": 5})
        assert "_source" in res
        assert res.get("_is_measured") is True
        assert res["total_population"] > 5_000_000  # Ahmedabad ~6.87M
        
        exposure = res["exposure_by_heat_severity"]
        assert exposure["extreme_heat_utci_46_plus"] > 0
        assert exposure["very_strong_heat_utci_42_to_46"] >= 0
        assert sum(exposure.values()) == res["total_population"]

        vuln = res["vulnerable_populations_citywide"]
        assert vuln["elderly_60_plus"] > 0
        assert vuln["infants_and_children_under_6"] > 0
        assert vuln["informal_tin_or_asbestos_roof_dwellers"] > 0
        assert vuln["outdoor_and_informal_laborers"] > 0

        assert len(res["top_exposed_wards"]) <= 5
        assert len(res["top_exposed_wards"]) > 0
        assert res["top_exposed_wards"][0]["total_population"] > 0

    def test_tool_is_present_in_tool_specs(self):
        spec_names = [s["function"]["name"] for s in TOOL_SPECS]
        assert "get_population_exposure" in spec_names


class TestChatAgentPopulationExposure:
    def test_agent_answers_population_at_risk_with_grounded_numbers(self):
        tool_data = execute_tool("get_population_exposure", {"top_n": 5})
        total_pop = tool_data["total_population"]
        extreme_pop = tool_data["exposure_by_heat_severity"]["extreme_heat_utci_46_plus"]
        elderly = tool_data["vulnerable_populations_citywide"]["elderly_60_plus"]

        provider = ScriptedProvider([
            LLMResponse(
                text=None,
                tool_calls=[ToolCall(name="get_population_exposure", args={"top_n": 5})],
                stop_reason="tool_use",
            ),
            LLMResponse(
                text=(
                    f"Across Ahmedabad, {extreme_pop} residents out of a total population of {total_pop} "
                    f"are exposed to extreme heat stress. Approximately {elderly} elderly residents live "
                    f"in high-vulnerability neighbourhoods."
                ),
                tool_calls=[],
                stop_reason="end_turn",
            ),
        ])

        response = ag.run_agent("How many people are at risk from this heatwave?", provider=provider)
        assert not response.refused, f"Was unexpectedly refused: {response.refusal_reason}"
        assert response.guard_passed, f"Numeric guard failed: {response.ungrounded_numbers}"
        assert str(extreme_pop) in response.answer
        assert str(total_pop) in response.answer
        assert str(elderly) in response.answer

    def test_casualty_and_death_toll_still_refused(self):
        """Even with population measured, mortality forecasts remain uncalibrated."""
        provider = ScriptedProvider([])
        for q in [
            "How many people will die in this heatwave?",
            "What is the death toll?",
            "Can you give me the casualty count?",
            "Exact number of deaths expected?",
        ]:
            response = ag.run_agent(q, provider=provider)
            assert response.refused, f"Question '{q}' should have been refused"
            assert response.refusal_reason == "death_count_uncalibrated"
            assert provider.calls == [], "Model should not have been called"
