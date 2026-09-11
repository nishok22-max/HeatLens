"""Turn a typed question into scenario parameters -- and refuse everything else.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
This is a **parser**, not a chatbot. It maps English onto the small set of levers
the physics can actually model, and hands those parameters to a pre-computed
grid. It never writes a number, never estimates, and never answers a question it
does not recognise.

That restraint is the design, not a limitation of effort. ``insight.py`` already
states the position: *"if an intervention cannot be modelled with what we have,
it is not offered rather than being faked"*, and ``recommended_actions`` is
documented as *"not an optimiser and not an LLM"*. A generative assistant bolted
onto this project would put invented prose exactly where its credibility lives.

WHY THE RULES LIVE HERE BUT RUN IN THE BROWSER
-----------------------------------------------
The simulator must answer with the wifi off, so the *matching* has to happen in
TypeScript. But rules written in TypeScript would sit outside ``pytest``. So the
rules are authored and tested here, then compiled by ``compile_intents()`` into
the baked payload; the frontend is a small matcher over that table.

The two regex engines are not identical, so ``compile_intents`` emits only a
subset both accept, and a test enforces it. A pattern that works in Python and
silently fails in JavaScript would take the whole panel down offline, where
there is no console to notice it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "INTENTS",
    "REFUSAL_RULES",
    "ScenarioRequest",
    "Refusal",
    "parse",
    "compile_intents",
    "JS_UNSAFE",
]

# Regex constructs Python accepts and JavaScript does not (or reads differently).
# Lookbehind is the dangerous one: supported in Python and in modern Chrome, but
# not in every engine the built page might be opened in, and a silent failure
# offline is unrecoverable.
JS_UNSAFE = (
    r"(?P<",        # named groups: Python syntax, JS uses (?<name>
    r"(?<=", r"(?<!",   # lookbehind
    r"(?#",         # comments
    r"\Z", r"\A",   # Python-only anchors
    r"(?i)",        # inline flags: JS needs them on the literal
)


@dataclass
class ScenarioRequest:
    """A recognised question, reduced to grid coordinates."""

    parameters: dict = field(default_factory=dict)
    matched: list = field(default_factory=list)
    # Parameters the question named more than one value for. "Compare 50% and
    # 90% shade" is a reasonable thing to type and the grid answers one point
    # at a time, so the extra value is carried here and surfaced rather than
    # silently dropped -- answering half a question without saying so is the
    # quiet version of getting it wrong.
    ambiguous: dict = field(default_factory=dict)

    @property
    def is_cooling(self) -> bool:
        return "shade" in self.parameters or "greening" in self.parameters

    @property
    def is_scheduling(self) -> bool:
        return "shift_start" in self.parameters


@dataclass
class Refusal:
    """A question the model cannot answer, with the reason it cannot."""

    reason: str
    kind: str            # "not_modelled" | "never_claim" | "unrecognised"
    detail: str = ""


# ---------------------------------------------------------------------------
# Intents -- the levers the physics can model
# ---------------------------------------------------------------------------

# Each entry: id, pattern, the parameter it sets, and how to read the captured
# group. ``value`` is used when the pattern carries no number of its own.
INTENTS = [
    {
        "id": "shift_start_am",
        "pattern": r"(?:shift|move|start|begin)[^.?!]{0,40}?(\d{1,2})\s*(?:am|a\.m\.|:00)?",
        "parameter": "shift_start",
        "transform": "hour",
        "examples": ["shift work to 6am", "move the working day to start at 5",
                     "start outdoor work at 7am"],
    },
    {
        # A bare "6am" after the verb-led rule has had its chance. "am" is
        # specific enough to mean a start time without guessing; a bare number
        # with no meridiem is left alone, because "50" in "50% shade" is not
        # an hour.
        "id": "shift_start_bare_am",
        "pattern": r"\b(\d{1,2})\s*(?:am|a\.m\.)\b",
        "parameter": "shift_start",
        "transform": "hour",
        "examples": ["delivery riders at 6am", "anything at 5 am"],
    },
    {
        "id": "shade_percent",
        "pattern": r"(?:shade|shading|tarpaulin|cover|canopy)[^.?!]{0,40}?(\d{1,3})\s*%",
        "parameter": "shade",
        "transform": "percent",
        "examples": ["shade 90% of the work areas", "add shading of 50%"],
    },
    {
        "id": "shade_percent_before",
        "pattern": r"(\d{1,3})\s*%(?=[^.?!]{0,20}?(?:shade|shading|cover|canopy))",
        "parameter": "shade",
        "transform": "percent",
        "examples": ["70% shade over work areas"],
    },
    {
        "id": "shade_plain",
        "pattern": r"\b(?:shade|shading|tarpaulins?|canop(?:y|ies))\b",
        "parameter": "shade",
        "transform": "default",
        "value": 0.7,
        "examples": ["what about shade", "add shade"],
    },
    {
        "id": "greening_percent",
        "pattern": r"(?:green|greening|tree|trees|vegetation|plant)[^.?!]{0,40}?(\d{1,3})\s*%",
        "parameter": "greening",
        "transform": "percent",
        "examples": ["greening of 50%", "plant trees over 20% more"],
    },
    {
        "id": "greening_percent_before",
        "pattern": r"(\d{1,3})\s*%(?=[^.?!]{0,20}?(?:green|greening|tree|vegetation))",
        "parameter": "greening",
        "transform": "percent",
        "examples": ["35% more greenery"],
    },
    {
        "id": "greening_plain",
        "pattern": r"\b(?:green|greening|greenery|trees|vegetation|park|parks)\b",
        "parameter": "greening",
        "transform": "default",
        "value": 0.35,
        "examples": ["what if we plant trees", "greening the hottest wards"],
    },
    {
        # A legitimate question, and the grid already holds the row: the
        # untreated baseline every other answer is measured against.
        "id": "baseline",
        "pattern": r"\b(?:do nothing|no action|business as usual|without (?:any )?(?:action|intervention)|baseline)\b",
        "parameter": "shade",
        "transform": "default",
        "value": 0.0,
        "examples": ["what if we do nothing", "business as usual"],
    },
    {
        "id": "persona_child",
        "pattern": r"\b(?:child|children|kid|kids|school)\b",
        "parameter": "persona",
        "transform": "literal",
        "value": "child",
        "examples": ["shade 50% for school children"],
    },
    {
        "id": "persona_elderly",
        "pattern": r"\b(?:elderly|older|old people|senior|seniors)\b",
        "parameter": "persona",
        "transform": "literal",
        "value": "elderly",
        "examples": ["shift work to 6am for elderly residents"],
    },
    {
        "id": "persona_delivery",
        "pattern": r"\b(?:delivery|courier|rider|riders)\b",
        "parameter": "persona",
        "transform": "literal",
        "value": "delivery",
        "examples": ["delivery riders at 6am"],
    },
    {
        "id": "persona_construction",
        "pattern": r"\b(?:construction|labour|labor|worker|workers|outdoor work)\b",
        "parameter": "persona",
        "transform": "literal",
        "value": "construction",
        "examples": ["shade 90% for construction workers"],
    },
]

# ---------------------------------------------------------------------------
# Refusals -- grounded in what the project already declares
# ---------------------------------------------------------------------------

# These map onto the ``omitted`` list already baked into insights.json by
# scripts/06_bake_web.py and live.py. The wording is not duplicated here: the
# matcher looks the entry up by ``omitted_item`` so there is one copy of the
# reason, and it stays the copy the panel already shows.
REFUSAL_RULES = [
    {
        "id": "hydration",
        "pattern": r"\b(?:water station|water stations|hydration|drinking water|ors)\b",
        "kind": "not_modelled",
        "omitted_item": "Water stations / hydration measures",
    },
    {
        "id": "headcount",
        "pattern": r"\b(?:how many people|number of people|headcount|how many residents|people at risk)\b",
        "kind": "not_modelled",
        "omitted_item": "People-at-risk headcount",
    },
    {
        # Real interventions this model genuinely cannot evaluate. Saying so
        # by name is more useful than a generic "not recognised", and it is
        # the same policy insight.py already applies to hydration: not offered
        # rather than faked.
        "id": "unmodelled_intervention",
        "pattern": r"\b(?:cooling cent|air condition|\bac\b|rest shelter|night shelter|more breaks|rest break|work.rest|night shift|fewer hours|reduce (?:the )?(?:working |work )?hours|shorter (?:working )?day)\w*",
        "kind": "not_modelled",
        "reason": ("Not something this model can simulate. It changes the heat "
                   "a person is exposed to only through the three levers it "
                   "models -- work hours, shade and greening. Cooling centres "
                   "are planned as a siting problem, which is a different "
                   "question from how hot a place is."),
    },
    {
        # PRD.md "Never claim": a death or hospital-admission count.
        "id": "casualties",
        "pattern": r"\b(?:how many (?:will )?(?:die|deaths?)|death toll|casualt|mortality count|hospitali)\w*",
        "kind": "never_claim",
        "reason": ("This model reports *relative* risk and is deliberately not "
                   "calibrated against death records, so it cannot give a "
                   "casualty count. An official who acted on a made-up number "
                   "and found it wrong would never trust the system again."),
    },
    {
        # PRD.md "Never claim": the word "validated".
        "id": "validated",
        "pattern": r"\b(?:validated|validation|proven|accurate|accuracy)\b",
        "kind": "never_claim",
        "reason": ("Not validated -- cross-checked. The spatial pattern is "
                   "cross-checked against a second satellite (Terra vs Aqua, "
                   "0.946 rank agreement) and the physics against thermofeel. "
                   "There is no air-temperature station network here, so no "
                   "claim of validation is available."),
    },
]

# The things that can actually be simulated. ``persona`` is a modifier -- it
# changes who an answer is about, it is not a question on its own.
LEVERS = {"shift_start", "shade", "greening"}

UNRECOGNISED = (
    "That is not one of the levers this model can simulate. It can answer "
    "questions about shifting outdoor work hours, shade over work areas, and "
    "greening the hottest zones. Name a time or a percentage -- for example "
    "\"shift work to 6am\", \"shade 90%\", or both at once."
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _apply(transform: str, raw, intent) -> object | None:
    if transform == "hour":
        hour = int(raw)
        return hour if 0 <= hour <= 23 else None
    if transform == "percent":
        pct = int(raw)
        return pct / 100.0 if 0 <= pct <= 100 else None
    if transform in ("default", "literal"):
        return intent["value"]
    raise ValueError(f"unknown transform {transform!r}")


def parse(question: str):
    """Read a question into grid parameters, or refuse it.

    Refusals are checked first and win outright. "How many people are at risk if
    we add shade?" contains a recognisable lever, and answering the shade half
    while ignoring the headcount would be a way of appearing to answer the
    question that was actually asked.
    """
    text = (question or "").strip().lower()
    if not text:
        return Refusal(reason=UNRECOGNISED, kind="unrecognised")

    for rule in REFUSAL_RULES:
        if re.search(rule["pattern"], text):
            return Refusal(reason=rule.get("reason", ""), kind=rule["kind"],
                           detail=rule.get("omitted_item", ""))

    parameters, matched, ambiguous = {}, [], {}
    for intent in INTENTS:
        # A more specific intent already satisfied this parameter; do not let a
        # bare keyword overwrite an explicit number ("shade 90%" must not be
        # downgraded to the 0.7 default by ``shade_plain``).
        if intent["parameter"] in parameters:
            continue
        matches = list(re.finditer(intent["pattern"], text))
        if not matches:
            continue
        values = []
        for found in matches:
            raw = found.group(1) if found.groups() else None
            value = _apply(intent["transform"], raw, intent)
            if value is not None and value not in values:
                values.append(value)
        if not values:
            continue
        parameters[intent["parameter"]] = values[0]
        if len(values) > 1:
            ambiguous[intent["parameter"]] = values
        matched.append(intent["id"])

    # A persona on its own is not a what-if. "What if we give workers more
    # breaks" contains the word "workers", and answering it with a
    # shift-hours result would be answering a question nobody asked -- a
    # confident wrong answer, which is worse than no answer at all. A lever
    # must be named before anything is simulated.
    if not (LEVERS & parameters.keys()):
        return Refusal(reason=UNRECOGNISED, kind="unrecognised")
    return ScenarioRequest(parameters=parameters, matched=matched,
                           ambiguous=ambiguous)


def compile_intents() -> list[dict]:
    """Emit the rule table for the browser, in a regex subset JavaScript shares.

    Only what the matcher needs travels: pattern, parameter, transform and any
    fixed value. Examples stay server-side -- they exist for the tests.
    """
    out = []
    for intent in INTENTS:
        _assert_js_safe(intent["pattern"], intent["id"])
        entry = {
            "id": intent["id"],
            "pattern": intent["pattern"],
            "parameter": intent["parameter"],
            "transform": intent["transform"],
        }
        if "value" in intent:
            entry["value"] = intent["value"]
        out.append(entry)
    return out


def compile_refusals() -> list[dict]:
    """The refusal table for the browser, same subset rule."""
    out = []
    for rule in REFUSAL_RULES:
        _assert_js_safe(rule["pattern"], rule["id"])
        out.append({k: v for k, v in rule.items() if k != "examples"})
    return out


def _assert_js_safe(pattern: str, name: str) -> None:
    for token in JS_UNSAFE:
        if token in pattern:
            raise ValueError(
                f"intent {name!r} uses {token!r}, which JavaScript's regex "
                "engine does not accept the same way. The browser matcher runs "
                "this pattern offline where a silent failure cannot be seen."
            )
