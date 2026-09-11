"""Tests for spatial, risk, vulnerability and advisory.

These layers carry the project's honesty guarantees as much as its arithmetic, so
a good share of what is asserted here is that caveats survive: that a placeholder
still announces itself, that an uncalibrated model still says so, and that
unverified translations are still flagged. Those properties are exactly the ones
that quietly rot when someone later "cleans up" the code.
"""

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from heatstress import advisory as ad
from heatstress import risk as rk
from heatstress import spatial as sp
from heatstress import vulnerability as vu

ROOT = Path(__file__).resolve().parents[1]

AHMEDABAD_BBOX = {"min_lat": 22.95, "max_lat": 23.10,
                  "min_lon": 72.50, "max_lon": 72.66}


class TestGrid:
    def test_covers_bbox_and_is_deterministic(self):
        first = sp.build_grid(AHMEDABAD_BBOX, 8)
        second = sp.build_grid(AHMEDABAD_BBOX, 8)
        assert first == second, "grid must be stable across runs"
        assert len(first) > 100

    def test_finer_resolution_gives_more_cells(self):
        assert len(sp.build_grid(AHMEDABAD_BBOX, 8)) > \
               len(sp.build_grid(AHMEDABAD_BBOX, 7))

    def test_polygon_ring_is_closed(self):
        cell = sp.build_grid(AHMEDABAD_BBOX, 8)[0]
        ring = sp.cell_polygon(cell)
        assert ring[0] == ring[-1], "GeoJSON rings must close"
        # 6 vertices + 1 closing point for an ordinary hexagon. The bound is a
        # range rather than exactly 7 because H3 is not purely hexagonal: each
        # resolution contains 12 pentagons (5 vertices), and cells neighbouring
        # them can carry an extra vertex.
        assert 6 <= len(ring) <= 8

    def test_every_polygon_in_the_grid_is_closed(self):
        for cell in sp.build_grid(AHMEDABAD_BBOX, 8):
            ring = sp.cell_polygon(cell)
            assert ring[0] == ring[-1]
            assert len(ring) >= 6

    def test_polygon_is_lon_lat_order(self):
        """GeoJSON is [lon, lat]. Getting this backwards puts Ahmedabad in Somalia."""
        cell = sp.build_grid(AHMEDABAD_BBOX, 8)[0]
        lon, lat = sp.cell_polygon(cell)[0]
        assert 72.0 < lon < 73.5
        assert 22.5 < lat < 23.5

    def test_geojson_structure(self):
        cells = sp.build_grid(AHMEDABAD_BBOX, 8)[:5]
        fc = sp.grid_geojson(cells, {cells[0]: {"wbgt": 33.4}})
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 5
        assert fc["features"][0]["properties"]["h3_index"] == cells[0]
        assert fc["features"][0]["properties"]["wbgt"] == 33.4
        json.dumps(fc)


class TestUrbanHeatOffset:
    def test_offsets_are_centred_on_zero(self):
        """We redistribute the coarse forecast across the city; we do not add heat."""
        intensity = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        assert float(np.mean(sp.urban_heat_offset(intensity, 3.0))) == \
            pytest.approx(0.0, abs=1e-9)

    def test_amplitude_scales_linearly(self):
        intensity = np.linspace(0, 1, 20)
        assert float(np.ptp(sp.urban_heat_offset(intensity, 4.0))) == \
            pytest.approx(2 * float(np.ptp(sp.urban_heat_offset(intensity, 2.0))))

    def test_hotter_cells_get_positive_offsets(self):
        intensity = np.array([0.0, 0.5, 1.0])
        offsets = sp.urban_heat_offset(intensity, 3.0)
        assert offsets[0] < 0 < offsets[2]

    def test_constant_intensity_gives_no_variation(self):
        offsets = sp.urban_heat_offset(np.full(10, 0.7), 3.0)
        assert np.allclose(offsets, 0.0)

    def test_composite_weights_green_and_water_negatively(self):
        cells = ["a", "b"]
        form = sp.UrbanIntensity(
            built={"a": 1.0, "b": 1.0}, roads={"a": 1.0, "b": 1.0},
            green={"a": 0.0, "b": 1.0}, water={"a": 0.0, "b": 0.0},
        )
        composite = form.composite(cells)
        assert composite[0] > composite[1], "green cover must cool a cell"


class TestLayerCoverage:
    """A layer with no coverage contributes nothing whatever its weight.

    On the shipped Ahmedabad surface ``built`` -- the largest weight in the
    formula -- is 0.0 in every zone, so what is really being mapped is road
    density. That is a real defect, and these tests exist so it stays visible
    in the output instead of living in a docstring nobody reads.
    """

    CELLS = ["a", "b"]

    def _form(self, built):
        return sp.UrbanIntensity(
            built={"a": built, "b": built}, roads={"a": 0.8, "b": 0.2},
            green={"a": 0.0, "b": 0.5}, water={"a": 0.0, "b": 0.0})

    def test_an_empty_layer_is_reported_dead(self):
        report = self._form(0.0).coverage(self.CELLS)
        assert report["built"]["dead"] is True
        assert report["built"]["effective_weight"] == 0.0
        assert report["roads"]["dead"] is False

    def test_a_populated_layer_carries_its_full_weight(self):
        report = self._form(0.6).coverage(self.CELLS)
        assert report["built"]["effective_weight"] == \
               sp.COMPOSITE_WEIGHTS["built"]
        assert report["built"]["covered_fraction"] == 1.0

    def test_partial_coverage_is_a_fraction_not_a_flag(self):
        """water is non-zero in 29% of real zones -- thin, but not dead."""
        report = self._form(0.5).coverage(self.CELLS)
        assert report["green"]["covered_fraction"] == 0.5
        assert report["green"]["dead"] is False

    def test_the_formatted_report_names_the_dead_layer_out_loud(self):
        text = sp.format_coverage(self._form(0.0).coverage(self.CELLS))
        assert "built" in text and "DEAD" in text

    def test_weights_match_the_formula_they_describe(self):
        """If someone retunes composite() and not this table, they diverge."""
        source = inspect.getsource(sp.UrbanIntensity.composite)
        for name, weight in sp.COMPOSITE_WEIGHTS.items():
            assert f"{weight:.2f} * {name}" in source, \
                f"{name} weight {weight} is not the one composite() applies"


class TestExposureResponse:
    def test_no_excess_risk_below_threshold(self):
        assert float(rk.relative_risk(20.0)) == pytest.approx(1.0)
        assert float(rk.relative_risk(rk.DEFAULT_WBGT_RESPONSE.mmt)) == \
            pytest.approx(1.0)

    def test_risk_rises_above_threshold(self):
        values = rk.relative_risk(np.array([28.0, 30.0, 32.0, 34.0]))
        assert np.all(np.diff(values) > 0)

    def test_uncertainty_band_brackets_the_central_estimate(self):
        low = float(rk.relative_risk(34.0, which="low"))
        central = float(rk.relative_risk(34.0, which="central"))
        high = float(rk.relative_risk(34.0, which="high"))
        assert low < central < high

    def test_default_response_declares_itself_uncalibrated(self):
        """The honesty guarantee. If this ever passes as calibrated by default,
        the system is claiming a local fit it does not have."""
        assert rk.DEFAULT_WBGT_RESPONSE.is_calibrated is False
        assert "not fitted" in rk.DEFAULT_WBGT_RESPONSE.source.lower()

    def test_calibrate_produces_a_calibrated_copy(self):
        fitted = rk.DEFAULT_WBGT_RESPONSE.calibrate(
            mmt=27.0, beta=0.025, beta_low=0.02, beta_high=0.03,
            source="AMC daily mortality 2015-2023")
        assert fitted.is_calibrated is True
        assert rk.DEFAULT_WBGT_RESPONSE.is_calibrated is False, "must not mutate"

    def test_lag_kernel_spreads_effect_forward(self):
        """A single hot day must still raise risk on the days that follow."""
        daily = np.array([26.0, 26.0, 36.0, 26.0, 26.0, 26.0])
        lagged = rk.lagged_relative_risk(daily)
        assert lagged[3] > 1.0, "day after the spike must carry excess risk"
        assert lagged[2] > lagged[3] > lagged[4]

    def test_lag_weights_are_normalised(self):
        assert sum(rk.DEFAULT_WBGT_RESPONSE.lag_weights) == pytest.approx(1.0)

    def test_normalise_hazard_is_bounded(self):
        hazard = rk.normalise_hazard(np.linspace(15, 45, 50))
        assert np.all((hazard >= 0.0) & (hazard <= 1.0))
        assert float(rk.normalise_hazard(20.0)) == 0.0


class TestVulnerability:
    def test_placeholder_declares_itself(self):
        """The single most important assertion in this file."""
        surface = vu.PlaceholderVulnerability().build(["a", "b"],
                                                      intensity=np.array([0.2, 0.8]))
        assert surface.is_placeholder is True
        assert "PLACEHOLDER" in surface.provenance
        assert all(v["is_placeholder"] for v in surface.as_dict().values())

    def test_vulnerability_does_not_vary_between_cells(self):
        """Documents the known limitation rather than hiding it: without ward
        demographics, vulnerability is a constant, so risk variation comes from
        hazard alone. If this ever starts varying, the docs must change too."""
        surface = vu.PlaceholderVulnerability().build(
            ["a", "b", "c"], intensity=np.array([0.1, 0.5, 0.9]))
        assert len(set(surface.vulnerability.tolist())) == 1

    def test_census_ward_vulnerability_is_measured_and_varies(self):
        import json
        vuln_path = ROOT / "data" / "processed" / "vulnerability_ahmedabad.json"
        if not vuln_path.exists():
            pytest.skip("vulnerability_ahmedabad.json missing")
        source = vu.CensusWardVulnerability(vuln_path)
        data = json.loads(vuln_path.read_text("utf-8"))
        sample_cells = list(data["cells"].keys())[:20]
        surface = source.build(sample_cells)
        assert surface.is_placeholder is False
        assert "MEASURED" in surface.provenance
        # Vulnerability varies across cells because ward demographics differ!
        assert len(set(surface.vulnerability.tolist())) > 1
        assert np.all((surface.vulnerability >= 0.0) & (surface.vulnerability <= 1.0))
        assert np.all((surface.exposure >= 0.0) & (surface.exposure <= 1.0))

    def test_risk_composition_is_bounded_and_monotonic(self):
        hazard = np.array([0.2, 0.5, 0.9])
        risk = vu.combine_risk(hazard, np.full(3, 0.5), np.full(3, 0.5))
        assert np.all((risk >= 0.0) & (risk <= 1.0))
        assert np.all(np.diff(risk) > 0)

    def test_measured_exposure_keeps_vulnerability_placeholder(self):
        """The D15 split: measuring population must NOT quietly upgrade the
        vulnerability half. The two are reported separately precisely so the
        measured one cannot lend credibility to the assumed one."""
        surface = vu.MeasuredPopulationVulnerability().build(
            ["a", "b"], exposure=np.array([0.1, 0.9]))
        assert surface.exposure_is_measured is True
        assert surface.is_placeholder is True          # vulnerability, still
        assert len(set(surface.vulnerability.tolist())) == 1
        flags = surface.as_dict()["a"]
        assert flags["exposure_is_measured"] is True
        assert flags["is_placeholder"] is True

    def test_measured_exposure_refuses_to_invent_data(self):
        """Without measured exposure this class must fail loudly rather than
        fall back to a proxy that would be indistinguishable downstream."""
        with pytest.raises(ValueError, match="measured exposure"):
            vu.MeasuredPopulationVulnerability().build(["a", "b"])

    def test_measured_exposure_breaks_the_hazard_degeneracy(self):
        """Why this step exists at all.

        With exposure derived from the hazard pattern, risk is a monotone
        transform of hazard and reorders nothing. With independent population
        it must be able to disagree -- a cooler but crowded zone outranking a
        hotter empty one.
        """
        hazard = np.array([0.9, 0.5])          # cell 0 hotter
        proxy = vu.PlaceholderVulnerability().build(
            ["hot_empty", "cool_crowded"], intensity=np.array([0.9, 0.5]))
        degenerate = vu.combine_risk(hazard, proxy.exposure, proxy.vulnerability)
        assert degenerate[0] > degenerate[1]

        measured = vu.MeasuredPopulationVulnerability().build(
            ["hot_empty", "cool_crowded"], exposure=np.array([0.02, 1.0]))
        real = vu.combine_risk(hazard, measured.exposure, measured.vulnerability)
        assert real[1] > real[0], "population must be able to outrank heat"

    def test_population_loader_refuses_partial_coverage(self, tmp_path):
        """A zone missing from the file must not become exposure 0 -- that
        reads as 'nobody at risk here', the worst possible silent failure."""
        processed = tmp_path / "data" / "processed"
        processed.mkdir(parents=True)
        (processed / "population_x.json").write_text(json.dumps({
            "source": {"provider": "WorldPop", "dataset": "wpgppop",
                       "year": 2020, "native_resolution_m": 100},
            "exposure_scaling": {"method": "density / p95"},
            "cells": {"a": {"exposure": 0.5}},
        }), encoding="utf-8")

        got, why = vu.load_population_exposure(tmp_path, "x", ["a", "b"])
        assert got is None and "missing" in why

        got, why = vu.load_population_exposure(tmp_path, "x", ["a"])
        assert got is not None and got.tolist() == [0.5]
        assert "WorldPop" in why

    def test_population_loader_absent_file_is_not_an_error(self, tmp_path):
        got, why = vu.load_population_exposure(tmp_path, "nocity", ["a"])
        assert got is None and "not found" in why

    def test_zero_exposure_collapses_risk(self):
        """Dangerous heat over an empty field is not a public-health emergency."""
        empty = float(vu.combine_risk(np.array([0.9]), np.array([1e-6]),
                                      np.array([0.5]))[0])
        peopled = float(vu.combine_risk(np.array([0.9]), np.array([0.9]),
                                        np.array([0.5]))[0])
        assert empty < peopled / 10


class TestAdvisory:
    @pytest.mark.parametrize("utci,expected", [
        (50.0, "Extreme"), (40.0, "Severe"), (34.0, "Moderate"),
        (28.0, "Minor"), (10.0, "Unknown"),
    ])
    def test_severity_bands(self, utci, expected):
        assert ad.severity_for(utci)[0] == expected

    def test_advisory_text_avoids_raw_numbers(self):
        """Advisory copy targets low-literacy readers. A WBGT figure in the body
        is meaningless to them and crowds out the actionable instruction."""
        for severity_utci in (50.0, 40.0, 34.0):
            text = ad.advisory_text(severity_utci, "en")
            assert "WBGT" not in text and "UTCI" not in text

    def test_unverified_languages_are_flagged(self):
        """Machine-composed translations must never be silently trusted: an
        earlier draft contained a Lao codepoint inside the Gujarati string."""
        assert ad.is_verified("en") is True
        assert ad.is_verified("hi") is False
        assert ad.is_verified("gu") is False

    def test_all_languages_cover_all_severities(self):
        severities = set(ad.ADVISORY_TEMPLATES["en"])
        for language, templates in ad.ADVISORY_TEMPLATES.items():
            assert set(templates) == severities, f"{language} is missing severities"

    def test_cap_xml_is_valid_and_marked_exercise(self):
        from xml.etree import ElementTree as ET
        advisory = ad.build_advisory("8842c8d341fffff", "Ahmedabad",
                                     "2010-05-21T14:00:00+05:30", 62.2, 33.8, 0)
        xml = ad.cap_alert(advisory)
        root = ET.fromstring(xml)
        ns = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
        # A prototype must never emit status 'Actual' -- that is what real
        # warning infrastructure acts on.
        assert root.find("c:status", ns).text == "Exercise"
        assert root.find("c:info/c:severity", ns).text == "Extreme"
        assert root.find("c:info/c:event", ns).text == "Extreme Heat"

    def test_cap_polygon_is_lat_lon_order(self):
        """CAP wants 'lat,lon'; GeoJSON gives [lon, lat]. Transposing correctly
        is the difference between alerting Ahmedabad and alerting the Indian Ocean."""
        advisory = ad.build_advisory("cell", "Ahmedabad",
                                     "2010-05-21T14:00:00+05:30", 50.0, 33.0, 0)
        xml = ad.cap_alert(advisory, polygon=[[72.58, 23.03], [72.59, 23.03],
                                              [72.58, 23.03]])
        first = xml.split("<polygon>")[1].split("</polygon>")[0].split()[0]
        lat, lon = (float(v) for v in first.split(","))
        assert 22.5 < lat < 23.5 and 72.0 < lon < 73.5

    def test_no_safe_work_note_when_zero_minutes(self):
        advisory = ad.build_advisory("cell", "Ahmedabad",
                                     "2010-05-21T14:00:00+05:30", 62.0, 33.8, 0)
        assert "No safe outdoor work" in advisory.safe_work_note
