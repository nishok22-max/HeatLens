"""Guard on the project's own go/no-go verdict.

This file lands BEFORE Phase 5 touches the urban-heat offset, and that ordering
is the whole point. The shipped margin is 0.88 degC -- a 3.88 degC spread
against a 3.0 degC threshold -- so swapping the assumed amplitude for a measured
satellite pattern could flip PROCEED to MARGINAL with nothing but a console line
to show for it. The last class here reads the committed cube, so that flip
becomes a failing test.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from heatstress import killgate as kg

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "config" / "ahmedabad.yaml").read_text(encoding="utf-8"))
CUBE_PATH = ROOT / "data" / "processed" / "indices_ahmedabad.npz"


class TestSpread:
    def test_is_max_minus_min(self):
        assert kg.spread([30.0, 33.5, 31.2]) == pytest.approx(3.5)

    def test_ignores_nan(self):
        """Cloud-blanked zones arrive as NaN in Phase 5; they must not win."""
        assert kg.spread([30.0, np.nan, 33.5]) == pytest.approx(3.5)

    def test_constant_field_has_zero_spread(self):
        assert kg.spread(np.full(10, 31.0)) == 0.0


class TestVerdict:
    def test_proceed_above_threshold(self):
        result = kg.verdict(2.0, 3.88, 3.0, 1.5)
        assert result.decision == kg.PROCEED
        assert result.margin_c == pytest.approx(0.88)

    def test_marginal_between_thresholds(self):
        assert kg.verdict(1.9, 2.2, 3.0, 1.5).decision == kg.MARGINAL

    def test_pivot_below_both(self):
        result = kg.verdict(0.8, 1.1, 3.0, 1.5)
        assert result.decision == kg.PIVOT
        assert result.margin_c < 0, "a failed gate reports how far it fell short"

    def test_boundaries_are_inclusive_at_the_lower_edge(self):
        assert kg.verdict(0.0, 3.0, 3.0, 1.5).decision == kg.PROCEED
        assert kg.verdict(0.0, 1.5, 3.0, 1.5).decision == kg.MARGINAL
        assert kg.verdict(0.0, 1.4999, 3.0, 1.5).decision == kg.PIVOT

    def test_strongest_index_drives_the_decision(self):
        """WBGT is damped in dry heat; UTCI is amplified. The larger wins."""
        assert kg.verdict(1.0, 3.5, 3.0, 1.5).driver == "UTCI"
        assert kg.verdict(3.5, 1.0, 3.0, 1.5).driver == "WBGT"

    def test_air_temperature_cannot_reach_the_verdict(self):
        """Air spread is an input, not a result. It is not an argument here."""
        assert "air" not in kg.verdict.__code__.co_varnames

    def test_inverted_thresholds_are_rejected(self):
        with pytest.raises(ValueError, match="inverted"):
            kg.verdict(3.0, 3.0, 1.5, 3.0)

    def test_headline_matches_the_decision(self):
        assert "map" in kg.verdict(0.0, 4.0, 3.0, 1.5).headline
        assert "persona" in kg.verdict(0.0, 0.1, 3.0, 1.5).headline


class TestFocusIndex:
    TIMESTAMPS = ["2010-05-21 13:00", "2010-05-21 14:00", "2010-05-21 15:00"]

    def test_finds_the_focus_hour(self):
        assert kg.focus_index(self.TIMESTAMPS, "2010-05-21", 14) == 1

    def test_missing_hour_raises_rather_than_scoring_the_wrong_one(self):
        """Silently scoring 03:00 would read as a genuine PIVOT."""
        with pytest.raises(LookupError):
            kg.focus_index(self.TIMESTAMPS, "2010-05-21", 3)


@pytest.mark.skipif(not CUBE_PATH.exists(),
                    reason="stored cube not present; run scripts/04 first")
class TestCommittedCube:
    """The real guard: the shipped numbers, scored by the shipped thresholds."""

    @staticmethod
    def _verdict():
        cube = np.load(CUBE_PATH, allow_pickle=False)
        gate, hind = CONFIG["kill_gate"], CONFIG["hindcast"]
        return kg.verdict_from_cube(cube, hind["focus_date"],
                                    hind["focus_hour_ist"],
                                    gate["proceed_spread_c"],
                                    gate["pivot_spread_c"])

    def test_the_shipped_verdict_is_proceed(self):
        assert self._verdict().decision == kg.PROCEED

    def test_the_margin_is_the_number_the_documents_quote(self):
        """3.43 degC, margin +0.43. If this moves, the documents are wrong.

        CHANGED ONCE, DELIBERATELY. It read 3.88 / +0.88 while the spatial
        pattern came from the OpenStreetMap composite with an assumed 3.0 degC
        amplitude. Replacing that with measured MODIS surface temperature and
        alpha = 0.40 gives a 2.68 degC air-temperature spread instead of a
        flat 3.00, so the UTCI spread fell to 3.43.

        This test failing is what surfaced the change rather than letting it
        land silently -- which is why it was written before the offsets moved.
        The verdict itself did not change: the premise holds on measured data,
        with less room than the assumed number flattered us into believing.
        """
        result = self._verdict()
        assert result.spread_c == pytest.approx(3.43, abs=0.02)
        assert result.margin_c == pytest.approx(0.43, abs=0.02)

    def test_the_verdict_now_depends_on_alpha_and_that_must_stay_visible(self):
        """THE VERDICT IS NO LONGER ROBUST ACROSS THE DECLARED ALPHA RANGE.

        Under the old assumed-amplitude method the gate passed across the whole
        literature range (2.57-6.53 degC), so the verdict did not depend on a
        flattering parameter choice. That is no longer true. With the measured
        satellite anomaly the UTCI spread is very close to linear in alpha:

            alpha 0.30 -> 2.57 degC  MARGINAL
            alpha 0.35 -> 3.00 degC  MARGINAL (on the threshold)
            alpha 0.40 -> 3.43 degC  PROCEED   <- config
            alpha 0.50 -> 4.29 degC  PROCEED

        So PROCEED holds for roughly the upper two thirds of ``alpha_range``
        and fails below about 0.35. This test exists so that fact cannot be
        quietly forgotten: anyone presenting the verdict must present the alpha
        sweep with it, exactly as the old method's amplitude sweep was.
        """
        lo, hi = CONFIG["urban_heat"]["alpha_range"]
        alpha = CONFIG["urban_heat"]["alpha"]
        result = self._verdict()
        # The spread scales with alpha to within the mild non-linearity of UTCI.
        at_low_end = result.spread_c * lo / alpha
        assert at_low_end < result.proceed_spread_c, (
            "The gate now passes across the whole alpha range. If that is "
            "genuinely true the claim in IMPLEMENTATION_PLAN §1 should be "
            "restored -- do not just delete this test.")
        assert result.spread_c * hi / alpha >= result.proceed_spread_c

    def test_utci_drives_it_and_wbgt_alone_would_not(self):
        """The damping finding, as an assertion: on dry heat WBGT falls short."""
        result = self._verdict()
        assert result.driver == "UTCI"
        assert result.wbgt_spread_c < result.proceed_spread_c
