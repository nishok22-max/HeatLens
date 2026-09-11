"""Tests for the what-if parser and the pre-baked scenario grid.

Two things are being defended here.

The first is that the parser **never guesses**. It is the only free-text surface
in a project whose entire claim is that its numbers are traceable, so an
unrecognised question must produce a refusal, not a plausible default.

The second is that the grid and the three headline cards can never disagree. They
are computed by the same functions, but by different call sites -- and a table
and a card showing different numbers for the same intervention would be worse
than having no table at all.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from heatstress import insight as ins
from heatstress import scenario_grid as sg
from heatstress import whatif as wi

ROOT = Path(__file__).resolve().parents[1]
INSIGHTS = ROOT / "web" / "data" / "insights.json"

# A small synthetic city: hot, dry, sunny -- the conditions the scenarios exist
# for. Defined here so no test depends on a pipeline run.
TA = np.array([44.0, 45.0, 46.0, 47.0])
RH = np.array([16.0, 15.0, 14.0, 13.0])
WIND = np.full(4, 3.0)
GHI = np.full(4, 900.0)
INTENSITY = np.array([0.1, 0.4, 0.7, 1.0])
WBGT_DAY = [26, 26, 27, 28, 29, 30, 31, 32, 33, 34, 34, 35, 35, 34,
            34, 33, 32, 31, 30, 29, 28, 27, 27, 26]


class TestParserRecognises:
    @pytest.mark.parametrize("question,expected", [
        ("shift work to 6am", {"shift_start": 6}),
        ("move the working day to start at 5", {"shift_start": 5}),
        ("shade 90% of the work areas", {"shade": 0.9}),
        ("70% shade over work areas", {"shade": 0.7}),
        ("what about shade", {"shade": 0.7}),
        ("35% more greenery", {"greening": 0.35}),
    ])
    def test_single_lever(self, question, expected):
        result = wi.parse(question)
        assert isinstance(result, wi.ScenarioRequest)
        assert result.parameters == expected

    def test_combination_is_the_whole_point(self):
        """Three fixed cards cannot express this; that is why the box exists."""
        result = wi.parse("shift work to 6am and shade 90%")
        assert result.parameters == {"shift_start": 6, "shade": 0.9}

    def test_an_explicit_number_beats_the_bare_keyword(self):
        """'shade 90%' must not be downgraded to the 0.7 default."""
        assert wi.parse("add shade of 90%").parameters["shade"] == 0.9

    def test_every_intent_parses_its_own_examples(self):
        """The examples are documentation; this stops them going stale."""
        for intent in wi.INTENTS:
            for example in intent["examples"]:
                result = wi.parse(example)
                assert isinstance(result, wi.ScenarioRequest), \
                    f"{intent['id']} example {example!r} was refused"
                assert intent["parameter"] in result.parameters, \
                    f"{intent['id']} example {example!r} set no {intent['parameter']}"

    def test_matched_intents_are_reported_for_the_trace(self):
        """The UI shows which rule fired; an unexplained answer is not grounded."""
        assert wi.parse("shift work to 6am").matched == ["shift_start_am"]


class TestParserDoesNotOverreach:
    """The defects found by running realistic phrasings through it.

    Each of these was a wrong answer rather than a missing one, which is the
    worse failure: a confident result to a question nobody asked.
    """

    def test_a_persona_alone_is_not_a_what_if(self):
        """'give workers more breaks' contains 'workers'. Answering it with a
        shift-hours result would answer a different question entirely."""
        for question in ("what about school children",
                         "is it safe for elderly people",
                         "delivery riders"):
            assert isinstance(wi.parse(question), wi.Refusal), question

    def test_a_persona_with_a_lever_is_fine(self):
        result = wi.parse("delivery riders at 6am")
        assert result.parameters == {"shift_start": 6, "persona": "delivery"}

    def test_two_values_for_one_lever_are_flagged_not_dropped(self):
        """Answering half a question without saying so is the quiet version of
        getting it wrong."""
        result = wi.parse("compare 50% and 90% shade")
        assert result.parameters["shade"] == 0.5
        assert result.ambiguous["shade"] == [0.5, 0.9]

    def test_a_single_value_is_not_flagged_as_ambiguous(self):
        assert wi.parse("shade 90%").ambiguous == {}

    def test_doing_nothing_is_a_real_question_with_a_real_row(self):
        assert wi.parse("what if we do nothing").parameters == {"shade": 0.0}

    @pytest.mark.parametrize("question", [
        "what if we give workers more breaks",
        "cooling centres",
        "air conditioning in schools",
        "reduce working hours",
        "night shift instead",
    ])
    def test_real_but_unmodelled_interventions_are_named_not_shrugged_at(
            self, question):
        """These are things a city genuinely does. Saying which ones the model
        cannot evaluate is more useful than 'not recognised'."""
        result = wi.parse(question)
        assert isinstance(result, wi.Refusal)
        assert result.kind == "not_modelled"

    def test_plurals_match(self):
        """'tarpaulins' silently matched nothing until a phrasing sweep."""
        assert wi.parse("would tarpaulins help").parameters == {"shade": 0.7}


class TestParserRefuses:
    def test_unrecognised_is_refused_not_defaulted(self):
        for question in ("who is the mayor", "what is the capital of Gujarat",
                         "asdfghjkl", ""):
            result = wi.parse(question)
            assert isinstance(result, wi.Refusal), f"{question!r} was answered"
            assert result.kind == "unrecognised"

    def test_hydration_maps_onto_the_existing_omitted_entry(self):
        """Reuse the reason already on screen rather than writing a new one."""
        result = wi.parse("what about water stations")
        assert result.kind == "not_modelled"
        assert result.detail == "Water stations / hydration measures"

    def test_headcount_is_refused_and_returns_no_number(self):
        result = wi.parse("how many people are at risk")
        assert isinstance(result, wi.Refusal)
        assert result.detail == "People-at-risk headcount"
        assert not any(ch.isdigit() for ch in result.reason)

    def test_a_refusal_wins_over_a_recognised_lever(self):
        """Answering the shade half would look like answering the question."""
        result = wi.parse("how many people are at risk if we add shade")
        assert isinstance(result, wi.Refusal)

    def test_casualty_questions_never_return_a_count(self):
        for question in ("how many will die", "what is the death toll",
                         "how many casualties", "hospitalisations?"):
            result = wi.parse(question)
            assert isinstance(result, wi.Refusal)
            assert result.kind == "never_claim"
            assert not any(ch.isdigit() for ch in result.reason)

    def test_the_word_validated_is_never_returned_as_a_claim(self):
        """PRD 'Never claim': say cross-checked, never validated."""
        result = wi.parse("is this validated")
        assert result.kind == "never_claim"
        assert "cross-checked" in result.reason
        assert "not validated" in result.reason.lower()


class TestCompiledForTheBrowser:
    def test_every_pattern_is_javascript_safe(self):
        """A pattern that fails only in JS takes the panel down offline, where
        there is no console to see it in."""
        for entry in wi.compile_intents() + wi.compile_refusals():
            for token in wi.JS_UNSAFE:
                assert token not in entry["pattern"], \
                    f"{entry['id']} uses JS-unsafe {token!r}"

    def test_an_unsafe_pattern_is_rejected_loudly(self):
        with pytest.raises(ValueError, match="JavaScript"):
            wi._assert_js_safe(r"(?<=x)y", "made_up")

    def test_compiled_table_carries_what_the_matcher_needs(self):
        for entry in wi.compile_intents():
            assert {"id", "pattern", "parameter", "transform"} <= set(entry)
            if entry["transform"] in ("default", "literal"):
                assert "value" in entry, f"{entry['id']} has no fixed value"

    def test_examples_stay_server_side(self):
        """They exist for the tests; shipping them bloats every page load."""
        assert all("examples" not in e for e in wi.compile_intents())


class TestGrid:
    @staticmethod
    def _grid():
        return sg.build_grid(TA, RH, WIND, GHI, INTENSITY, 2.68, WBGT_DAY)

    def test_shape_matches_the_declared_axes(self):
        grid = self._grid()
        assert len(grid["cooling"]) == len(sg.SHADE_AXIS) * len(sg.GREENING_AXIS)
        assert len(grid["scheduling"]) == len(sg.SHIFT_START_AXIS) * len(sg.PERSONA_AXIS)

    def test_more_shade_never_makes_it_hotter(self):
        rows = [r for r in self._grid()["cooling"] if r["greening"] == 0.0]
        temps = [r["utci_after"] for r in sorted(rows, key=lambda r: r["shade"])]
        assert temps == sorted(temps, reverse=True)

    def test_more_greening_never_makes_it_hotter(self):
        rows = [r for r in self._grid()["cooling"] if r["shade"] == 0.0]
        temps = [r["utci_after"] for r in sorted(rows, key=lambda r: r["greening"])]
        assert temps == sorted(temps, reverse=True)

    def test_doing_nothing_changes_nothing(self):
        row = next(r for r in self._grid()["cooling"]
                   if r["shade"] == 0.0 and r["greening"] == 0.0)
        assert row["delta_c"] == 0.0
        assert row["utci_after"] == row["utci_before"]

    def test_every_split_shift_beats_the_unshifted_day(self):
        """The invariant that actually holds. Taking the middle of the day out
        of the working hours cannot make things worse, whatever the start."""
        for row in self._grid()["scheduling"]:
            assert row["unsafe_after"] <= row["unsafe_before"], row

    def test_the_best_start_is_read_off_the_grid_not_assumed(self):
        """An earlier start is NOT automatically better, and this test exists to
        stop someone 'fixing' the grid into monotonic order.

        ``shift_window`` moves the whole split shift, so starting earlier also
        pulls the *evening* block earlier -- into the afternoon. Whether that
        loses more than the early morning gains depends entirely on the shape of
        the day: on the real Ahmedabad heatwave the earliest start wins, and on
        the synthetic day here (which never cools at night) the latest one does.
        That data-dependence is precisely why the grid is computed rather than a
        6 a.m. recommendation being hardcoded.
        """
        rows = [r for r in self._grid()["scheduling"]
                if r["persona"] == "construction"]
        best = min(rows, key=lambda r: r["unsafe_after"])
        assert best["shift_start"] in sg.SHIFT_START_AXIS
        assert len({r["unsafe_after"] for r in rows}) > 1, \
            "the start hour must actually change the answer"

    def test_the_grid_and_the_headline_card_agree(self):
        """The card and the table are computed by different call sites. If they
        ever disagree, one of them is lying to the user."""
        card = ins.scenario_shade(TA, RH, WIND, GHI, shade_fraction=0.7)
        row = next(r for r in self._grid()["cooling"]
                   if r["shade"] == 0.7 and r["greening"] == 0.0)
        assert row["utci_after"] == card["utci_after"]
        assert row["delta_c"] == card["delta_c"]

    def test_greening_reports_the_zones_it_treated(self):
        row = next(r for r in self._grid()["cooling"] if r["greening"] == 0.5)
        assert row["zones_treated"] > 0
        assert row["zones_treated"] < len(INTENSITY) + 1


class TestSnapping:
    def test_an_exact_value_does_not_report_a_snap(self):
        assert sg.nearest(0.7, sg.SHADE_AXIS) == (0.7, False)

    def test_an_off_grid_value_snaps_and_says_so(self):
        snapped, was_snapped = sg.nearest(0.8, sg.SHADE_AXIS)
        assert snapped in (0.7, 0.9) and was_snapped

    def test_nothing_is_interpolated(self):
        """D21: no manufacturing plausible-looking values between real ones."""
        snapped, _ = sg.nearest(0.62, sg.SHADE_AXIS)
        assert snapped in sg.SHADE_AXIS


class TestShiftWindow:
    def test_the_default_is_unchanged(self):
        """Generalising the window must not move the shipped card's numbers."""
        assert ins.shift_window(6) == ins.SHIFTED

    def test_the_working_day_stays_the_same_length(self):
        """Otherwise a shorter day would report lost work as a safety gain."""
        for start in sg.SHIFT_START_AXIS:
            assert len(ins.shift_window(start)) == len(ins.SHIFTED)

    def test_hours_wrap_within_the_day(self):
        assert all(0 <= h <= 23 for h in ins.shift_window(23))

    def test_an_impossible_start_is_rejected(self):
        with pytest.raises(ValueError):
            ins.shift_window(26)

    def test_window_is_described_as_a_scheduler_would_read_it(self):
        assert ins._describe_shift(ins.shift_window(6)) == \
               "06:00-11:00 and 17:00-21:00"


@pytest.mark.skipif(not INSIGHTS.exists(), reason="web data not baked yet")
class TestBakedPayload:
    @staticmethod
    def _load():
        return json.loads(INSIGHTS.read_text(encoding="utf-8"))

    def test_the_grid_and_rules_are_baked_for_offline_use(self):
        data = self._load()
        for key in ("scenario_grid", "intents", "refusals"):
            assert key in data, f"{key} missing; the ask box cannot work offline"

    def test_every_baked_intent_still_parses_something(self):
        ids = {i["id"] for i in self._load()["intents"]}
        assert ids == {i["id"] for i in wi.INTENTS}

    def test_refusals_can_reach_the_omitted_entries_shown_on_screen(self):
        data = self._load()
        shown = {o["item"] for o in data["omitted"]}
        referenced = {r["omitted_item"] for r in data["refusals"]
                      if "omitted_item" in r}
        assert referenced <= shown, "a refusal points at an entry not on screen"
