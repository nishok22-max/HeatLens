"""Tests for the satellite export -- pure functions only, no network, no credential.

Every payload here is synthetic and defined in this file. That is the point:
the 6-hourly job runs this suite on a machine with no Earth Engine credentials,
so importing ``sources.gee`` must not initialise anything, and nothing under
test may reach for a socket.

What is asserted is mostly the class of error that would otherwise be silent: a
missed scale factor, an anomaly measured against a reference polluted by
unmeasured zones, a thin zone quietly counted as observed.
"""

import json
from pathlib import Path

import h3
import numpy as np
import pytest
import yaml

from heatstress.sources import gee

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "config" / "ahmedabad.yaml").read_text(encoding="utf-8"))

# A handful of real Ahmedabad H3 cells, so parent grouping behaves as it does
# in production rather than on invented indices.
CELLS = sorted(h3.grid_disk(h3.latlng_to_cell(23.03, 72.58, 8), 2))


def make_rows(temps, valid_px=500):
    """Synthetic per-zone reductions: one temperature per cell, all thick."""
    return {cell: {"lst_c": t, "valid_px": valid_px, "ndvi": 0.2,
                   "ndbi": 0.1, "built_s": 0.4, "population": 1000.0}
            for cell, t in zip(CELLS, temps)}


class TestImportIsInert:
    def test_importing_does_not_initialise_earth_engine(self):
        """Rule 1. If this fails, the 6-hourly job dies on a credential-less box."""
        source = gee.GEESurfaceSource(cache_dir=ROOT / "data" / "raw")
        assert source._ee is None, "ee must not be touched until first use"

    def test_module_source_has_no_import_time_initialize(self):
        text = Path(gee.__file__).read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith(("import ", "from ")) and " ee" in line:
                pytest.fail(f"top-level Earth Engine import: {line!r}")


class TestUnits:
    def test_scale_and_offset_give_a_plausible_temperature(self):
        """A hot Ahmedabad May surface reads about 49,500 in raw counts."""
        assert gee.surface_temperature_c(49500) == pytest.approx(
            49500 * gee.ST_SCALE + gee.ST_OFFSET - 273.15, abs=1e-6)
        assert 40.0 < gee.surface_temperature_c(49500) < 60.0

    def test_missing_scale_factor_is_caught(self):
        """Raw digital numbers are ~1000x too large. Silent otherwise."""
        with pytest.raises(ValueError, match="scale factor"):
            gee.assert_surface_temperature_plausible([49500.0, 45000.0])

    def test_missing_offset_is_caught(self):
        """Scale applied, offset forgotten: about -104 degC."""
        scaled_only = 49500 * gee.ST_SCALE - 273.15
        with pytest.raises(ValueError, match="scale factor"):
            gee.assert_surface_temperature_plausible([scaled_only])

    def test_kelvin_instead_of_celsius_is_caught(self):
        with pytest.raises(ValueError):
            gee.assert_surface_temperature_plausible([317.0, 320.0])

    def test_hot_indian_rooftops_are_not_rejected(self):
        """Bare tarmac in May genuinely reaches the high 50s. Not an error."""
        gee.assert_surface_temperature_plausible([28.0, 58.0])

    def test_all_nan_is_rejected(self):
        with pytest.raises(ValueError, match="no finite values"):
            gee.assert_surface_temperature_plausible([np.nan, np.nan])


class TestBuildCells:
    def test_anomalies_are_measured_against_the_city_mean(self):
        temps = np.linspace(40.0, 50.0, len(CELLS))
        records, city_mean = gee.build_cells(make_rows(temps), CELLS, 200)
        assert city_mean == pytest.approx(float(np.mean(temps)))
        anomalies = [r["lst_anomaly_c"] for r in records.values()]
        assert sum(anomalies) == pytest.approx(0.0, abs=1e-6), \
            "anomalies redistribute heat; they must not add any"

    def test_thin_zones_are_excluded_and_say_so(self):
        rows = make_rows(np.full(len(CELLS), 45.0))
        thin = CELLS[0]
        rows[thin]["valid_px"] = 12
        records, _ = gee.build_cells(rows, CELLS, 200)
        assert records[thin]["provenance"] == gee.INSUFFICIENT_PIXELS
        assert records[thin]["lst_c"] is None
        assert records[thin]["lst_anomaly_c"] is None
        assert records[CELLS[1]]["provenance"] == gee.OBSERVED

    def test_the_city_mean_ignores_unmeasured_zones(self):
        """A thin zone must not drag the reference every anomaly is measured from."""
        temps = np.full(len(CELLS), 45.0)
        rows = make_rows(temps)
        rows[CELLS[0]].update({"lst_c": 5.0, "valid_px": 3})
        _, city_mean = gee.build_cells(rows, CELLS, 200)
        assert city_mean == pytest.approx(45.0)

    def test_provenance_is_a_label_not_a_boolean(self):
        """Phase 5C adds a third value, 'modelled'. A bool could not carry it."""
        records, _ = gee.build_cells(make_rows(np.full(len(CELLS), 45.0)),
                                     CELLS, 200)
        assert isinstance(records[CELLS[0]]["provenance"], str)

    def test_a_missing_cell_is_reported_not_invented(self):
        rows = make_rows(np.full(len(CELLS), 45.0))
        del rows[CELLS[0]]
        records, _ = gee.build_cells(rows, CELLS, 200)
        assert records[CELLS[0]]["provenance"] == gee.INSUFFICIENT_PIXELS
        assert records[CELLS[0]]["valid_px"] == 0

    def test_no_usable_zone_raises_rather_than_writing_an_empty_map(self):
        rows = make_rows(np.full(len(CELLS), 45.0), valid_px=1)
        with pytest.raises(ValueError, match="unusable"):
            gee.build_cells(rows, CELLS, 200)

    def test_unit_error_survives_into_the_zone_builder(self):
        with pytest.raises(ValueError, match="scale factor"):
            gee.build_cells(make_rows(np.full(len(CELLS), 44000.0)), CELLS, 200)


class TestCoverage:
    def test_counts_and_verdict(self):
        rows = make_rows(np.full(len(CELLS), 45.0))
        for cell in CELLS[:2]:
            rows[cell]["valid_px"] = 5
        records, _ = gee.build_cells(rows, CELLS, 200)
        summary = gee.coverage_summary(records, 0.90)
        assert summary["cells_total"] == len(CELLS)
        assert summary["cells_insufficient_pixels"] == 2
        assert summary["cells_observed"] + 2 == summary["cells_total"]
        assert summary["passes"] == (summary["observed_fraction"] >= 0.90)

    def test_full_coverage_passes(self):
        records, _ = gee.build_cells(make_rows(np.full(len(CELLS), 45.0)),
                                     CELLS, 200)
        assert gee.coverage_summary(records, 0.90)["passes"]


class TestChunking:
    def test_chunks_cover_everything_exactly_once(self):
        items = list(range(392))
        chunks = gee.chunked(items, 100)
        assert len(chunks) == 4
        assert [x for chunk in chunks for x in chunk] == items

    def test_rejects_a_zero_chunk_size(self):
        with pytest.raises(ValueError):
            gee.chunked([1, 2, 3], 0)

    def test_cache_key_depends_on_the_request(self):
        source = gee.GEESurfaceSource(cache_dir=ROOT / "data" / "raw")
        a = source._cache_path("zones", {"cells": CELLS[:2]})
        b = source._cache_path("zones", {"cells": CELLS[:3]})
        assert a != b, "different requests must not share a cache entry"
        assert a == source._cache_path("zones", {"cells": CELLS[:2]}), \
            "the same request must hit the same cache entry, or nothing resumes"


class TestRankAgreement:
    def test_identical_ordering_is_one(self):
        assert gee.rank_agreement([1, 2, 3, 4], [10, 20, 30, 40]) == \
               pytest.approx(1.0)

    def test_reversed_ordering_is_minus_one(self):
        assert gee.rank_agreement([1, 2, 3, 4], [40, 30, 20, 10]) == \
               pytest.approx(-1.0)

    def test_is_rank_based_not_value_based(self):
        """MODIS and Landsat measure at different times and scales. Only the
        ordering is expected to match, so a monotone rescale must not change it."""
        a = [1.0, 2.0, 3.0, 4.0]
        b = [x ** 3 + 5 for x in a]
        assert gee.rank_agreement(a, b) == pytest.approx(1.0)

    def test_too_few_blocks_returns_nan_instead_of_a_number(self):
        assert np.isnan(gee.rank_agreement([1, 2], [1, 2]))

    def test_ignores_missing_values(self):
        assert gee.rank_agreement([1, 2, np.nan, 4], [1, 2, 99, 4]) == \
               pytest.approx(1.0)


class TestModisCrossCheck:
    def test_compares_only_observed_zones_and_reports_block_count(self):
        temps = np.linspace(40.0, 50.0, len(CELLS))
        rows = make_rows(temps)
        rows[CELLS[0]]["valid_px"] = 1
        records, _ = gee.build_cells(rows, CELLS, 200)
        blocks = sorted({h3.cell_to_parent(c, 6) for c in CELLS})
        modis = {b: 40.0 + i for i, b in enumerate(blocks)}

        check = gee.modis_cross_check(records, modis, 6)
        assert check["n_blocks"] == len(blocks)
        assert set(check["blocks"]) <= set(blocks)
        assert check["instrument"] == gee.MODIS_AQUA_LST
        assert "never mixed in" in check["note"]

    def test_survives_a_block_modis_could_not_measure(self):
        records, _ = gee.build_cells(make_rows(np.linspace(40, 50, len(CELLS))),
                                     CELLS, 200)
        blocks = sorted({h3.cell_to_parent(c, 6) for c in CELLS})
        modis = {b: None for b in blocks}
        check = gee.modis_cross_check(records, modis, 6)
        assert check["n_blocks"] == 0
        assert check["rank_agreement"] is None


class TestConfigContract:
    """The script reads these keys. They were dead config for weeks; if one
    disappears again, the export fails at the satellite, not in review."""

    def test_composite_keys_exist(self):
        composite = CONFIG["urban_heat"]["lst_composite"]
        for key in ("years", "months", "max_cloud_cover_pct",
                    "min_valid_px_per_cell", "min_scenes"):
            assert key in composite, f"lst_composite.{key} is missing"

    def test_alpha_is_present_and_inside_its_own_sweep_range(self):
        uhi = CONFIG["urban_heat"]
        lo, hi = uhi["alpha_range"]
        assert lo <= uhi["alpha"] <= hi

    def test_the_pass_mark_is_declared_before_any_model_is_fitted(self):
        """It only means something if it is in the file before the fit exists."""
        assert CONFIG["urban_heat"]["downscale"]["min_spatial_cv_r2"] == 0.25

    def test_population_source_is_named(self):
        assert CONFIG["population"]["source"] == "JRC/GHSL/P2023A/GHS_POP"


@pytest.mark.skipif(
    not (ROOT / "data" / "processed" / "satellite_ahmedabad.json").exists(),
    reason="satellite export not run yet; needs Earth Engine authorisation")
class TestExportedFile:
    """Runs only once the export exists. Then it guards what it contains."""

    @staticmethod
    def _load():
        return json.loads(
            (ROOT / "data" / "processed" / "satellite_ahmedabad.json")
            .read_text(encoding="utf-8"))

    def test_enough_scenes_to_call_it_a_composite(self):
        out = self._load()
        assert out["scenes"]["n_scenes"] >= out["scenes"]["min_scenes"]

    def test_every_zone_declares_its_provenance(self):
        for record in self._load()["cells"].values():
            assert record["provenance"] in (gee.OBSERVED,
                                            gee.INSUFFICIENT_PIXELS)

    def test_observed_temperatures_are_in_celsius(self):
        temps = [r["lst_c"] for r in self._load()["cells"].values()
                 if r["lst_c"] is not None]
        gee.assert_surface_temperature_plausible(temps)

    def test_the_file_says_surface_temperature_not_air_temperature(self):
        out = self._load()
        assert "city_mean_lst_c" in out
        assert "d_ta_c" not in json.dumps(out["cells"][next(iter(out["cells"]))])
