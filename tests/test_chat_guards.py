"""
tests/test_chat_guards.py — Phase 5G

Unit tests for the numeric guard and refusal table.
These tests require no LLM key and no internet access.
They pin the guard and refusal logic against fixed inputs so they cannot
pass or fail depending on live data — the same principle used in §7.10.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ---------------------------------------------------------------------------
# Refusal table
# ---------------------------------------------------------------------------

class TestRefusalTable:
    def setup_method(self):
        from heatstress.chat.guards import RefusalTable
        self.rt = RefusalTable()

    def _check(self, q):
        return self.rt.check(q)

    # Must refuse
    def test_refuses_people_at_risk(self):
        assert self._check("How many people are at risk?") is not None

    def test_refuses_death_count(self):
        assert self._check("What is the death count from this heatwave?") is not None

    def test_refuses_casualties(self):
        assert self._check("How many casualties were there?") is not None

    def test_refuses_fatalities(self):
        assert self._check("Expected fatalities this summer?") is not None

    def test_refuses_headcount(self):
        assert self._check("Give me a headcount of people exposed") is not None

    def test_refuses_validated(self):
        assert self._check("Is HeatLens validated?") is not None

    def test_refuses_clinically_validated(self):
        assert self._check("Is this clinically validated?") is not None

    def test_refuses_how_many_will_die(self):
        assert self._check("How many will die if temperatures spike?") is not None

    # Must allow
    def test_allows_peak_utci(self):
        assert self._check("What is the peak UTCI?") is None

    def test_allows_hottest_zone(self):
        assert self._check("Which zone is hottest?") is None

    def test_allows_work_window(self):
        assert self._check("When can construction workers go outside?") is None

    def test_allows_advisory(self):
        assert self._check("What does the advisory say?") is None

    def test_allows_drivers(self):
        assert self._check("Why is UTCI higher than WBGT here?") is None

    def test_allows_methodology(self):
        assert self._check("How does the thermal model work?") is None

    def test_refuses_returns_version(self):
        """Refusal result must carry a version number for auditability."""
        result = self._check("How many people are at risk?")
        assert result is not None
        assert isinstance(result.rule_version, int)
        assert result.rule_version >= 1

    def test_refuses_returns_reason(self):
        result = self._check("How many people are at risk?")
        assert result is not None
        assert result.reason  # must be non-empty string

    def test_case_insensitive(self):
        assert self._check("HOW MANY PEOPLE ARE AT RISK?") is not None
        assert self._check("is heatlens validated?") is not None

    def test_allows_population_queries_when_measured(self):
        from heatstress.chat.guards import RefusalTable
        rt = RefusalTable(has_population_data=True)
        assert rt.check("How many people are at risk?") is None
        assert rt.check("Give me a headcount of people exposed") is None
        assert rt.check("What is the population at risk?") is None
        # But casualty and death questions are STILL refused!
        assert rt.check("What is the death count?") is not None
        assert rt.check("How many casualties were there?") is not None
        assert rt.check("How many will die?") is not None
        assert rt.check("What is the death toll?") is not None


# ---------------------------------------------------------------------------
# Numeric guard
# ---------------------------------------------------------------------------

class TestNumericGuard:
    def setup_method(self):
        from heatstress.chat.guards import NumericGuard
        self.guard = NumericGuard()

    # --- Passing cases ---

    def test_grounded_number_passes(self):
        result = self.guard.check(
            "The peak UTCI is 62.2 °C, which is Extreme severity.",
            [{"utci_c": 62.2, "_source": "city.json"}],
        )
        assert result.passed

    def test_no_numbers_no_tools_passes(self):
        result = self.guard.check(
            "The data comes from Open-Meteo ERA5 archive.",
            [],
        )
        assert result.passed

    def test_exempt_numbers_pass(self):
        """Small prose ordinals (1, 2, 3…) are exempt."""
        result = self.guard.check(
            "There are 3 recommended actions: step 1, step 2, step 3.",
            [],
        )
        assert result.passed

    def test_question_numbers_pass(self):
        """Numbers echoed from the question are exempt."""
        result = self.guard.check(
            answer="Zone 8842 has a UTCI of 62.2 °C.",
            tool_returns=[{"utci_c": 62.2, "_source": "city.json"}],
            question="Tell me about zone 8842.",
        )
        assert result.passed

    def test_number_inside_source_tag_passes(self):
        """Numbers buried inside the source path should count as grounded."""
        result = self.guard.check(
            "The UTCI spread is 3.88 °C across the city.",
            [{"utci_spread_c": 3.88, "_source": "web/data/meta.json"}],
        )
        assert result.passed

    # --- Failing cases ---

    def test_invented_number_fails(self):
        result = self.guard.check(
            "The temperature is 99.9 °C.",
            [{"utci_c": 62.2, "_source": "city.json"}],
        )
        assert not result.passed
        assert "99.9" in result.ungrounded

    def test_no_tools_with_number_fails(self):
        result = self.guard.check(
            "There are 18420 people at risk.",
            [],
        )
        assert not result.passed

    def test_ungrounded_returns_ungrounded_list(self):
        result = self.guard.check(
            "The risk is 999.0.",
            [{"utci_c": 62.2}],
        )
        assert not result.passed
        assert "999.0" in result.ungrounded

    def test_multiple_grounded_numbers(self):
        result = self.guard.check(
            "UTCI is 62.2 °C and WBGT is 33.8 °C.",
            [{"utci_c": 62.2, "wbgt_c": 33.8, "_source": "advisory.json"}],
        )
        assert result.passed

    def test_guard_result_has_message(self):
        result = self.guard.check("Temperature is 99.9 °C.", [{"ta": 42.0}])
        assert result.message
