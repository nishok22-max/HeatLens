"""Tests for the MODIS satellite path -- the source that ships the measured pattern.

No network. Every payload is synthetic and defined here, except the last class,
which guards the committed export file itself.

The emphasis is on the errors that would be silent: a mirrored city, quality
flags applied to the wrong date, a scale factor forgotten, a zone sampled from a
pixel two kilometres away and reported as a measurement.
"""

import json
import math
from pathlib import Path

import h3
import numpy as np
import pytest
import yaml

from heatstress import satellite as sat
from heatstress import spatial as sp
from heatstress.sources import modis_ornl as mo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "config" / "ahmedabad.yaml").read_text(encoding="utf-8"))
EXPORT = ROOT / "data" / "processed" / "satellite_ahmedabad.json"
OFFSETS = ROOT / "data" / "processed" / "urban_form_lst_ahmedabad.json"

# The real header ORNL returns for the shipping Ahmedabad subset
# (kmAboveBelow=10), so the geometry under test is the geometry in production.
# The +-9 km subset used while exploring is 19x19 and falls ~0.4 km short of the
# southern edge of the bounding box, which is why the config asks for 10.
HEADER = {"xllcorner": "7417636.59", "yllcorner": "2550999.85",
          "cellsize": 926.6254330558338, "nrows": 21, "ncols": 21}


class TestProjection:
    def test_round_trips_through_the_forward_projection(self):
        for lat, lon in ((23.03, 72.58), (0.0, 0.0), (-33.9, 151.2)):
            x = mo.SINUSOIDAL_RADIUS_M * math.radians(lon) * math.cos(
                math.radians(lat))
            y = mo.SINUSOIDAL_RADIUS_M * math.radians(lat)
            back_lat, back_lon = mo.sinusoidal_to_latlng(x, y)
            assert back_lat == pytest.approx(lat, abs=1e-9)
            assert back_lon == pytest.approx(lon, abs=1e-9)

    def test_row_zero_is_the_northernmost_row(self):
        """Getting this backwards mirrors the city and leaves every value plausible.

        Verified against the live service during development: the coordinates
        this function returns for pixel 0 were sent back as a single-pixel
        request and returned the identical digital number.
        """
        lat, _ = mo.pixel_centres(HEADER)
        assert lat[0] > lat[-1], "row 0 must be north of the last row"
        top_row = lat[:HEADER["ncols"]]
        assert np.allclose(top_row, top_row[0]), "one row shares one latitude"

    def test_grid_covers_the_city_bounding_box(self):
        lat, lon = mo.pixel_centres(HEADER)
        bbox = CONFIG["city"]["bbox"]
        assert lat.min() < bbox["min_lat"] and lat.max() > bbox["max_lat"]
        assert lon.min() < bbox["min_lon"] and lon.max() > bbox["max_lon"]

    def test_pixel_spacing_matches_the_declared_cell_size(self):
        lat, _ = mo.pixel_centres(HEADER)
        step_km = (lat[0] - lat[HEADER["ncols"]]) * 111.32
        assert step_km == pytest.approx(HEADER["cellsize"] / 1000, abs=0.02)

    def test_one_coordinate_per_data_value(self):
        lat, lon = mo.pixel_centres(HEADER)
        assert lat.size == lon.size == HEADER["nrows"] * HEADER["ncols"]


class TestQuality:
    def test_good_quality_is_kept(self):
        assert mo.quality_mask(np.array([0b00000000]))[0]

    def test_not_produced_is_rejected(self):
        """Mandatory bits 10 and 11 mean the pixel was never retrieved."""
        assert not mo.quality_mask(np.array([0b10]))[0]
        assert not mo.quality_mask(np.array([0b11]))[0]

    def test_other_quality_within_two_kelvin_is_kept(self):
        """The documented screen for general use, and the one this project runs."""
        qc = 0b01 | (1 << 6)          # produced/other quality, error <= 2 K
        assert mo.quality_mask(np.array([qc]))[0]

    def test_large_error_is_rejected(self):
        qc = 0b01 | (3 << 6)          # error > 3 K
        assert not mo.quality_mask(np.array([qc]))[0]

    def test_the_strict_screen_is_available_and_stricter(self):
        qc = np.array([0b01 | (1 << 6)])
        assert mo.quality_mask(qc, max_error_class=1)[0]
        assert not mo.quality_mask(qc, max_error_class=0)[0]


class TestComposite:
    def test_scales_to_celsius(self):
        """15941 * 0.02 - 273.15 = 45.67 C, a real Ahmedabad April value."""
        mean, _ = mo.composite_pixels([[15941]], [[0]])
        assert mean[0] == pytest.approx(45.67, abs=0.01)

    def test_fill_value_is_excluded(self):
        mean, obs = mo.composite_pixels([[15941], [0]], [[0], [0]])
        assert mean[0] == pytest.approx(45.67, abs=0.01)
        assert obs[0] == 1, "a fill value is not an observation"

    def test_masked_observations_do_not_drag_the_mean(self):
        lst = [[15941], [16941]]
        qc = [[0b00], [0b10]]         # second one not produced
        mean, obs = mo.composite_pixels(lst, qc)
        assert mean[0] == pytest.approx(45.67, abs=0.01)
        assert obs[0] == 1

    def test_a_pixel_with_nothing_usable_is_nan_not_zero(self):
        mean, obs = mo.composite_pixels([[15941]], [[0b10]])
        assert np.isnan(mean[0]), "zero would read as a freezing city block"
        assert obs[0] == 0

    def test_mismatched_stacks_are_refused(self):
        """Pairing by position would apply one date's clouds to another's heat."""
        with pytest.raises(ValueError, match="disagree"):
            mo.composite_pixels([[1], [2]], [[0]])


class TestSampling:
    """Nearest pixel centre, with a distance guard."""

    CELLS = sp.build_grid(CONFIG["city"]["bbox"], 8)

    def _grid(self, value=45.0, obs=20, offset=0.0):
        lat, lon = h3.cell_to_latlng(self.CELLS[0])
        return mo.PixelGrid(lat=np.array([lat + offset]),
                            lon=np.array([lon]),
                            value_c=np.array([value]),
                            n_obs=np.array([obs]), n_composites=21,
                            product=mo.AQUA, band="LST_Day_1km",
                            cellsize_m=926.6)

    def test_a_zone_takes_the_value_of_the_pixel_it_sits_in(self):
        rows = self._grid(value=46.5)
        out = mo.sample_zones(rows, [self.CELLS[0]], min_obs=5)
        assert out[self.CELLS[0]]["lst_c"] == pytest.approx(46.5)
        assert out[self.CELLS[0]]["sample_distance_km"] < 0.1

    def test_a_distant_pixel_is_not_a_measurement(self):
        """0.05 degrees is ~5.5 km away: that is extrapolation, not data."""
        out = mo.sample_zones(self._grid(offset=0.05), [self.CELLS[0]],
                              min_obs=5, max_distance_km=1.0)
        assert out[self.CELLS[0]]["lst_c"] is None
        assert out[self.CELLS[0]]["valid_px"] == 0

    def test_thin_pixels_are_not_used(self):
        with pytest.raises(ValueError, match="no usable"):
            mo.sample_zones(self._grid(obs=2), [self.CELLS[0]], min_obs=5)

    def test_no_interpolation_is_invented(self):
        """Two zones sharing a pixel must report the identical number.

        At 1 km the pixel is about the size of a zone, so smoothing would
        manufacture sub-pixel detail the instrument never resolved. Blocky and
        true beats smooth and invented.
        """
        grid = self._grid(value=44.0)
        out = mo.sample_zones(grid, self.CELLS[:2], min_obs=5,
                              max_distance_km=50.0)
        assert out[self.CELLS[0]]["lst_c"] == out[self.CELLS[1]]["lst_c"]


class TestSharedContract:
    """``satellite.py`` holds the schema both sources must produce."""

    CELLS = sorted(h3.grid_disk(h3.latlng_to_cell(23.03, 72.58, 8), 2))

    def _rows(self, day=45.0, night=27.0):
        return {c: {"lst_c": day + i * 0.1, "valid_px": 20,
                    "lst_night_c": night + i * 0.1}
                for i, c in enumerate(self.CELLS)}

    def test_night_layer_has_its_own_city_mean(self):
        """Night anomalies measured against the day mean would be nonsense."""
        rows = self._rows()
        records, day_mean = sat.build_cells(rows, self.CELLS, 5)
        night_mean = sat.add_night_layer(records, rows)
        assert night_mean < day_mean - 10
        anomalies = [r["lst_night_anomaly_c"] for r in records.values()]
        assert sum(anomalies) == pytest.approx(0.0, abs=1e-6)

    def test_night_is_optional(self):
        rows = {c: {"lst_c": 45.0, "valid_px": 20} for c in self.CELLS}
        records, _ = sat.build_cells(rows, self.CELLS, 5)
        assert sat.add_night_layer(records, rows) is None

    def test_a_night_unit_error_is_caught_too(self):
        rows = self._rows(night=300.0)      # kelvin, not celsius
        records, _ = sat.build_cells(rows, self.CELLS, 5)
        with pytest.raises(ValueError, match="night LST"):
            sat.add_night_layer(records, rows)

    def test_cross_check_compares_blocks_not_zones(self):
        rows = self._rows()
        records, _ = sat.build_cells(rows, self.CELLS, 5)
        other = {c: rows[c]["lst_c"] + 3.0 for c in self.CELLS}
        check = sat.cross_check_blocks(records, other, 6, "MOD11A2")
        assert check["n_blocks"] < len(self.CELLS)
        assert check["rank_agreement"] == pytest.approx(1.0)

    def test_cross_check_notices_a_reversed_pattern(self):
        rows = self._rows()
        records, _ = sat.build_cells(rows, self.CELLS, 5)
        other = {c: -rows[c]["lst_c"] for c in self.CELLS}
        assert sat.cross_check_blocks(records, other, 6, "x")[
            "rank_agreement"] == pytest.approx(-1.0)


class TestResolver:
    def test_prefers_the_measured_file(self):
        path, level = sp.resolve_urban_form(ROOT, "ahmedabad", "lst")
        assert level == "lst"
        assert path.name == "urban_form_lst_ahmedabad.json"

    def test_osm_mode_deliberately_skips_it(self):
        """This is what makes the before/after comparison a one-key re-run."""
        path, level = sp.resolve_urban_form(ROOT, "ahmedabad", "osm_composite")
        assert level == "osm"
        assert path.name == "urban_form_ahmedabad.json"

    def test_falls_back_to_the_placeholder_for_an_unknown_city(self):
        _, level = sp.resolve_urban_form(ROOT, "atlantis", "lst")
        assert level == "placeholder"


@pytest.mark.skipif(not OFFSETS.exists(), reason="satellite offsets not built")
class TestCommittedOffsets:
    """Guards on the file the whole product is now computed from."""

    @staticmethod
    def _load():
        return json.loads(OFFSETS.read_text(encoding="utf-8"))

    def test_every_zone_has_the_two_keys_downstream_reads(self):
        for record in self._load()["cells"].values():
            assert isinstance(record["d_ta_c"], float)
            assert 0.0 <= record["intensity"] <= 1.0

    def test_offsets_sum_to_zero(self):
        """A redistribution of the city forecast, not extra heat added to it."""
        values = [r["d_ta_c"] for r in self._load()["cells"].values()]
        assert np.mean(values) == pytest.approx(0.0, abs=1e-3)

    def test_the_air_offset_is_alpha_times_the_surface_anomaly(self):
        out = self._load()
        for record in out["cells"].values():
            assert record["d_ta_c"] == pytest.approx(
                out["alpha"] * record["lst_anomaly_c"], abs=1e-3)

    def test_surface_anomaly_is_bigger_than_the_air_offset(self):
        """Surface UHI exceeds air UHI. If this ever inverts, alpha is wrong."""
        out = self._load()
        surface = [r["lst_anomaly_c"] for r in out["cells"].values()]
        air = [r["d_ta_c"] for r in out["cells"].values()]
        assert np.ptp(surface) > np.ptp(air)
        assert out["alpha"] < 1.0

    def test_every_zone_declares_how_it_got_its_number(self):
        for record in self._load()["cells"].values():
            assert record["provenance"] in sat.PROVENANCE_VALUES

    def test_most_zones_are_measured_not_filled(self):
        records = self._load()["cells"].values()
        observed = sum(1 for r in records if r["provenance"] == sat.OBSERVED)
        assert observed / len(records) >= 0.90

    def test_the_independent_instrument_still_agrees(self):
        """Terra vs Aqua. A collapse here means the pattern stopped being real."""
        check = self._load()["cross_check"]
        assert check["rank_agreement"] >= 0.5, check
        assert check["n_blocks"] >= 10

    def test_night_temperatures_are_cooler_than_day(self):
        out = self._load()
        assert out["night_city_mean_lst_c"] < out["city_mean_lst_c"]
