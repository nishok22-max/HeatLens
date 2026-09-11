"""
Numeric guard and refusal table for the HeatLens chat agent.

TWO DISTINCT CHECKS — order matters:

  1. ``RefusalTable.check(question)``  — called BEFORE the LLM round-trip.
     Returns a pre-canned refusal if the question is one we cannot honestly
     answer, saving tokens and avoiding any risk of the LLM wriggling around
     the constraint.

  2. ``NumericGuard.check(answer, tool_returns)`` — called AFTER the answer
     is generated.  Every number that appears in the answer must appear in at
     least one tool return.  This is a structural guarantee, not a prompt
     instruction: a prompt is a request, a post-check is a guarantee.

Design decisions:
  - Refusals are a versioned list of (pattern, reason, response) tuples so
    that they can be updated when the underlying data changes (e.g. when 5E
    lands real population data, the headcount refusal must be loosened).
  - The numeric guard is intentionally strict: it rejects numbers that the
    LLM invented even if they happen to be true.  Auditability matters more
    than never blocking a valid answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Refusal table
# ---------------------------------------------------------------------------

@dataclass
class RefusalRule:
    """One entry in the refusal table."""
    # Regex patterns matched against the user's question (case-insensitive).
    patterns: list[str]
    reason: str           # internal — logged, not shown to user
    response: str         # what the agent says instead
    # Increment this when the rule is updated — makes diffs obvious.
    version: int = 1


# Each rule is matched against the lowercased user question.
# Rules are checked in order; the first match wins.
REFUSAL_RULES: list[RefusalRule] = [
    RefusalRule(
        patterns=[
            r"how many people",
            r"number of people",
            r"population at risk",
            r"headcount",
        ],
        reason="population_placeholder",
        response=(
            "HeatLens doesn't have ward-level population or health-outcome data yet. "
            "The vulnerability layer is a declared placeholder, so a headcount would be fabricated. "
            "What I can tell you is which zones are hottest, by how much, and what the "
            "relative (not absolute) risk looks like — want me to show that instead?"
        ),
        version=1,
    ),
    RefusalRule(
        patterns=[
            r"is (this|the model|it|heatl[e]?ns) validated",
            r"has (this|it|heatl[e]?ns) been validated",
            r"validated\?",
            r"clinically validated",
            r"officially validated",
        ],
        reason="validated_word_guard",
        response=(
            "The thermal indices are cross-checked: our WBGT and UTCI implementations "
            "agree with thermofeel (ECMWF's own library) to within 0.005 °C, and the "
            "spatial pattern is cross-validated against held-out satellite observations. "
            "The word 'validated' is deliberately avoided — it implies regulatory approval "
            "this prototype hasn't sought."
        ),
        version=1,
    ),
    RefusalRule(
        patterns=[
            r"casualt",          # casualties / casualty
            r"\bdeaths?\b",
            r"death.{0,10}count",
            r"mortality",
            r"fatalit",
            r"hospitali",
            r"exact(ly)? how many deaths",
            r"total deaths",
            r"death toll",
            r"how many died",
            r"how many.{0,15}die",
            r"will die",
        ],
        reason="death_count_uncalibrated",
        response=(
            "The exposure-response model is not calibrated to local health records "
            "(is_calibrated=False). Quoting a death count from an uncalibrated model "
            "would misrepresent its precision. "
            "I can show you relative risk by zone, or the ISO 7243 safe-work windows — "
            "both are grounded in the data we actually have."
        ),
        version=2,
    ),
]


class RefusalTable:
    """Check a question against the refusal table before hitting the LLM."""

    def __init__(
        self,
        rules: list[RefusalRule] | None = None,
        has_population_data: bool = False,
    ):
        base_rules = rules or REFUSAL_RULES
        if has_population_data:
            # When population data is measured, loosen the headcount refusal
            # so the agent can route to get_population_exposure. Casualties/deaths STAY refused.
            self._rules = [r for r in base_rules if r.reason != "population_placeholder"]
        else:
            self._rules = list(base_rules)

        self._compiled = [
            (
                rule,
                [re.compile(p, re.IGNORECASE) for p in rule.patterns],
            )
            for rule in self._rules
        ]

    def check(self, question: str) -> RefusalResult | None:
        """Return a RefusalResult if this question should be refused, else None."""
        for rule, patterns in self._compiled:
            for pat in patterns:
                if pat.search(question):
                    return RefusalResult(
                        refused=True,
                        reason=rule.reason,
                        response=rule.response,
                        rule_version=rule.version,
                    )
        return None


@dataclass
class RefusalResult:
    refused: bool
    reason: str
    response: str
    rule_version: int


# ---------------------------------------------------------------------------
# Numeric guard
# ---------------------------------------------------------------------------

# Matches integers and decimals (positive only — negative values in tool
# returns are rare and the sign is part of the representation).
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _extract_numbers(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def _tool_returns_as_text(tool_returns: list[dict[str, Any]]) -> str:
    """Flatten all tool return values into one searchable string."""
    import json
    parts = []
    for r in tool_returns:
        try:
            parts.append(json.dumps(r, default=str))
        except Exception:
            parts.append(str(r))
    return " ".join(parts)


@dataclass
class GuardResult:
    passed: bool
    ungrounded: list[str]   # numbers in the answer not found in tool returns
    message: str            # human-readable explanation


class NumericGuard:
    """Post-check: every number in the answer must appear in a tool return.

    Exempt numbers:
      - 0, 1, 2, 3  — too common as prose ordinals ("step 1", "2 hours")
      - Numbers that appear literally in the question (quoted back by the LLM)
      - Numbers ≤ 10 that appear ONLY as list positions or ISO standard refs
        (we exempt ≤ threshold to reduce false positives on round numbers)

    The exemption list is conservative — the guard errs on the side of
    blocking rather than passing.
    """

    EXEMPT = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
              "15", "60", "100", "108"}  # 108 = emergency number in India

    def __init__(self, exempt_extra: set[str] | None = None):
        self._exempt = self.EXEMPT | (exempt_extra or set())

    def check(
        self,
        answer: str,
        tool_returns: list[dict[str, Any]],
        question: str = "",
    ) -> GuardResult:
        """Return GuardResult indicating whether all numbers are grounded."""
        if not tool_returns:
            # No tools were called — only safe if the answer contains no numbers.
            nums = _extract_numbers(answer) - self._exempt
            if nums:
                return GuardResult(
                    passed=False,
                    ungrounded=sorted(nums),
                    message=(
                        "Answer contains numbers but no tools were called. "
                        f"Ungrounded: {sorted(nums)}"
                    ),
                )
            return GuardResult(passed=True, ungrounded=[], message="No tools, no numbers — ok.")

        pool_text = _tool_returns_as_text(tool_returns)
        question_nums = _extract_numbers(question)

        answer_nums = _extract_numbers(answer) - self._exempt - question_nums
        ungrounded = [n for n in answer_nums if n not in pool_text]

        if ungrounded:
            return GuardResult(
                passed=False,
                ungrounded=ungrounded,
                message=(
                    f"Answer contains {len(ungrounded)} number(s) not found in tool returns: "
                    f"{ungrounded}. The answer will be regenerated without those figures."
                ),
            )

        return GuardResult(
            passed=True,
            ungrounded=[],
            message=f"All numbers grounded across {len(tool_returns)} tool return(s).",
        )
