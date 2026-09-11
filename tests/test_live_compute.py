"""Tests for the live compute path, run offline against the cached forecast.

Two things are being defended here. The first is ordinary: the payload has the
shape every downstream consumer assumes. The second is the reason this project
recomputes every five minutes at all -- the focus hour is "the peak stress hour
*ahead*", so it moves with the wall clock even when the weather payload has not
changed. If that stops being true, the refresh interval stops being justified.

The regression guard at the bottom is for a real bug: `scripts/07_live.py` and
`api/services/engine.py` each once replaced thermofeel's Liljegren WBGT with a
different function at import time. One crashed; the other silently served
different physics than the hindcast.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from heatstress import insight as ins
from heatstress import live
from heatstress.sources import openmeteo as om

IST = timezone(timedelta(hours=5.5))


@pytest.fixture(scope="module")
def cached_forecast():
    """The committed Open-Meteo response, so these tests never touch the network."""
    config = live.ROOT / "config" / "ahmedabad.yaml"
    if not config.exists():                       # pragma: no cover
        pytest.skip("config/ahmedabad.yaml missing")
    import yaml
    centre = yaml.safe_load(config.read_text(encoding="utf-8"))["city"]["centre"]
    try:
        return om.fetch_forecast(centre["lat"], centre["lon"],
                                 max_age_minutes=10 ** 9)   # cache only, never refetch
    except Exception as exc:                      # pragma: no cover
        pytest.skip(f"no cached forecast available: {exc}")


@pytest.fixture
def offline(monkeypatch, cached_forecast):
    monkeypatch.setattr(om, "fetch_forecast",
                        lambda *a, **k: cached_forecast)
    monkeypatch.setattr(om, "forecast_age_minutes", lambda *a, **k: 7.0)


@pytest.fixture(scope="module")
def payload(cached_forecast, monkeypatch_module=None):
    import heatstress.live as _live
    original = om.fetch_forecast, om.forecast_age_minutes
    om.fetch_forecast = lambda *a, **k: cached_forecast
    om.forecast_age_minutes = lambda *a, **k: 7.0
    try:
        return _live.compute_live()
    finally:
        om.fetch_forecast, om.forecast_age_minutes = original


class TestPayloadShape:
    def test_has_every_key_the_api_serves(self, payload):
        assert set(payload) == set(live.PAYLOAD_FILES)

    def test_hourly_covers_every_cell(self, payload):
        assert len(payload["hourly"]["hexes"]) == payload["meta"]["n_cells"]

    def test_map_is_a_feature_collection_of_every_cell(self, payload):
        assert payload["map"]["type"] == "FeatureCollection"
        assert len(payload["map"]["features"]) == payload["meta"]["n_cells"]

    def test_focus_index_is_inside_the_series(self, payload):
        idx = live.focus_index(payload)
        assert 0 <= idx < len(payload["summary"]["timestamps_ist"])

    def test_mode_is_live_and_carries_a_timestamp(self, payload):
        assert payload["meta"]["mode"] == "live"
        assert payload["meta"]["generated_at_ist"]

    def test_the_whole_payload_is_json_serialisable(self, payload):
        """Anything else and atomic_write_json refuses to publish it."""
        import json
        json.dumps(payload, ensure_ascii=False)


class TestFocusMovesWithTheClock:
    def test_focus_advances_once_now_passes_the_peak(self, offline):
        """The justification for recomputing on an interval.

        The focus is not merely "the hottest hour" -- it is the hottest hour
        still ahead. So it holds steady while the peak is in the future and
        jumps the moment the clock passes it. Both halves matter: the first is
        why the display is stable, the second is why we recompute at all.
        """
        stamps = live.compute_live()["summary"]["timestamps_ist"]
        early = datetime.strptime(stamps[0], "%Y-%m-%d %H:%M").replace(tzinfo=IST)

        first = live.compute_live(now=early)["meta"]["focus"]
        past_peak = (datetime.strptime(f"{first['date']} {first['hour_ist']:02d}:00",
                                       "%Y-%m-%d %H:%M").replace(tzinfo=IST)
                     + timedelta(hours=1))
        second = live.compute_live(now=past_peak)["meta"]["focus"]

        assert (second["date"], second["hour_ist"]) > (first["date"],
                                                       first["hour_ist"])

    def test_focus_is_never_in_the_past(self, offline):
        stamps = live.compute_live()["summary"]["timestamps_ist"]
        mid = datetime.strptime(stamps[len(stamps) // 2], "%Y-%m-%d %H:%M")
        result = live.compute_live(now=mid.replace(tzinfo=IST))
        focus = result["meta"]["focus"]
        assert f"{focus['date']} {focus['hour_ist']:02d}" >= mid.strftime("%Y-%m-%d %H")


class TestHonestyGuaranteesSurvive:
    """The provenance flags are the product, not decoration."""

    def test_uhi_amplitude_is_still_declared_assumed(self, payload):
        statuses = " ".join(layer["status"] for layer in payload["meta"]["provenance"])
        assert "ASSUMED" in statuses

    def test_vulnerability_provenance_is_explicit(self, payload):
        vulnerability = [layer for layer in payload["meta"]["provenance"]
                         if "vulnerab" in layer["layer"].lower()]
        assert vulnerability, "vulnerability layer vanished from provenance"
        status = vulnerability[0]["status"].upper()
        assert "MEASURED" in status or "NOT FITTED" in status

    def test_exposure_response_is_still_uncalibrated(self, payload):
        assert payload["meta"]["exposure_response"]["is_calibrated"] is False

    def test_caveats_are_not_empty(self, payload):
        assert len(payload["meta"]["caveats"]) >= 3


class TestSettings:
    def test_defaults_come_from_the_module_constants(self):
        settings = live.load_settings("config/ahmedabad.yaml")
        assert settings.interval_seconds > 0
        assert settings.max_age_minutes > 0

    def test_explicit_arguments_win(self):
        settings = live.load_settings("config/ahmedabad.yaml",
                                      interval=42, max_age=7)
        assert settings.interval_seconds == 42
        assert settings.max_age_minutes == 7

    def test_missing_config_falls_back_to_constants(self, tmp_path):
        settings = live.load_settings(tmp_path / "nope.yaml")
        assert settings.interval_seconds == live.LIVE_REFRESH_SECONDS
        assert settings.max_age_minutes == live.LIVE_MAX_AGE_MINUTES

    def test_forecast_ttl_is_under_the_upstream_hourly_cadence(self):
        """A TTL above an hour would sit on data Open-Meteo already replaced."""
        assert live.LIVE_MAX_AGE_MINUTES < 60


def test_nothing_monkeypatches_thermofeel():
    """Guard the seam that two modules independently got wrong.

    `heatstress.live` is imported above; if anyone reintroduces an import-time
    patch anywhere on that graph, the real signature stops matching.
    """
    import thermofeel
    params = inspect.signature(thermofeel.calculate_wbgt_liljegren).parameters
    assert len(params) >= 7
    assert "cossza" in params


class TestPartDayIsScoredByHourNotPosition:
    """A forecast window's first and last local dates are part-days.

    `insight.scenario_shift_hours` asks for specific clock hours (06:00-21:00).
    It used to index the day series by list position, which silently assumed
    position == hour-of-day. That holds for a complete midnight-to-midnight day
    and fails for a part-day: every hour is mis-addressed, and a short tail
    raised IndexError through `live.compute_live`. These cases pin the contract
    against fixed inputs, so they do not pass or fail depending on the wall
    clock the way the failure originally did.
    """

    def _flat_day(self, wbgt=32.0):
        return [wbgt] * 24, list(range(24))

    def test_a_part_day_does_not_raise(self):
        """The original bug: a 14-hour tail, asked about hour 20."""
        series = [32.0] * 14
        hours = list(range(10, 24))
        result = ins.scenario_shift_hours(series, hours=hours)
        assert result["key"] == "shift_hours"

    def test_a_part_day_reports_that_it_is_partial(self):
        result = ins.scenario_shift_hours([32.0] * 14, hours=list(range(10, 24)))
        assert result["covers_full_shift"] is False
        assert "Partial" in result["basis"]

    def test_a_complete_day_reports_that_it_is_exact(self):
        series, hours = self._flat_day()
        result = ins.scenario_shift_hours(series, hours=hours)
        assert result["covers_full_shift"] is True
        assert result["basis"].startswith("Exact")

    def test_hours_are_addressed_by_clock_not_position(self):
        """Hot afternoon, cool evening, offered only from 12:00.

        Positional indexing would read entry 9 (21:00, cool) as "09:00" and get
        a different answer. Clock addressing must score 09:00 as absent.
        """
        hours = list(range(12, 24))
        series = [40.0 if h < 18 else 24.0 for h in hours]
        result = ins.scenario_shift_hours(series, hours=hours)
        positional = ins.scenario_shift_hours(series)
        assert result["unsafe_before"] != positional["unsafe_before"]

    def test_omitting_hours_still_matches_the_old_full_day_behaviour(self):
        """The hindcast path passes no `hours`; its numbers must not move."""
        series, hours = self._flat_day()
        assert (ins.scenario_shift_hours(series)["unsafe_before"]
                == ins.scenario_shift_hours(series, hours=hours)["unsafe_before"])

    def test_uncovered_hours_are_excluded_from_both_sides(self):
        """Not silently treated as safe, which would flatter the comparison."""
        full, hours = self._flat_day(38.0)
        partial = ins.scenario_shift_hours(full[:18], hours=hours[:18])
        assert partial["hours_scored"] < ins.scenario_shift_hours(full, hours=hours)["hours_scored"]
