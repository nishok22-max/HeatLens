import type { HeatData } from "./types";

/**
 * Two layers: the baked dataset bundled at build time, and a live overlay
 * fetched from the API when one is reachable.
 *
 * WHY THE BUNDLE IS STILL HERE, now that there is an API:
 * Chromium treats a page loaded from file:// as an opaque origin and blocks
 * fetch()/XHR against sibling file:// URLs. A fetch-only build therefore works
 * over http in dev and silently renders blank the moment the demo is opened
 * straight from disk — which is exactly the scenario NFR-1 exists to guarantee,
 * and exactly the scenario you would discover on stage. It is also what the
 * GitHub Pages deploy serves, where there is no localhost to reach.
 *
 * So the bundle is the floor: the page always has data before any request is
 * made. The API is an enhancement on top, and a failed fetch degrades to "the
 * numbers are a little old" rather than to an error page.
 *
 * `?raw` is used uniformly so the .geojson extension needs no special Vite
 * config, and so every file travels the same code path.
 */
import metaRaw from "../../web/data/meta.json?raw";
import hexesRaw from "../../web/data/hexes.geojson?raw";
import hourlyRaw from "../../web/data/hourly.json?raw";
import cityRaw from "../../web/data/city.json?raw";
import personasRaw from "../../web/data/personas.json?raw";
import advisoryRaw from "../../web/data/advisory.json?raw";
import insightsRaw from "../../web/data/insights.json?raw";

import liveMetaRaw from "../../web/data/live/meta.json?raw";
import liveHexesRaw from "../../web/data/live/hexes.geojson?raw";
import liveHourlyRaw from "../../web/data/live/hourly.json?raw";
import liveCityRaw from "../../web/data/live/city.json?raw";
import livePersonasRaw from "../../web/data/live/personas.json?raw";
import liveAdvisoryRaw from "../../web/data/live/advisory.json?raw";
import liveInsightsRaw from "../../web/data/live/insights.json?raw";

export type DatasetKey = "historical" | "live";

export const DATASET_META: Record<DatasetKey, { label: string; sub: string }> = {
  historical: {
    label: "May 2010 heatwave",
    sub: "the event that killed ~1,344 people",
  },
  live: {
    label: "Forecast",
    sub: "now and the next few days",
  },
};

/** The UI calls the second dataset "live"; the API namespaces it "forecast".
 *  One map, so the two names cannot silently drift apart again. */
const ROUTE: Record<DatasetKey, string> = {
  historical: "historical",
  live: "forecast",
};

/** Origin of the FastAPI backend (`uvicorn api.main:app`). One variable, because
 *  there is one backend -- an earlier split across two names let the health probe
 *  and the data fetch point at different servers without anything complaining. */
export const API_ORIGIN: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const API_BASE = `${API_ORIGIN}/api/v1`;

export const BUNDLED: Record<DatasetKey, HeatData> = {
  historical: {
    meta: JSON.parse(metaRaw),
    hexes: JSON.parse(hexesRaw),
    hourly: JSON.parse(hourlyRaw),
    city: JSON.parse(cityRaw),
    personas: JSON.parse(personasRaw),
    advisory: JSON.parse(advisoryRaw),
    insights: JSON.parse(insightsRaw),
  },
  live: {
    meta: JSON.parse(liveMetaRaw),
    hexes: JSON.parse(liveHexesRaw),
    hourly: JSON.parse(liveHourlyRaw),
    city: JSON.parse(liveCityRaw),
    personas: JSON.parse(livePersonasRaw),
    advisory: JSON.parse(liveAdvisoryRaw),
    insights: JSON.parse(liveInsightsRaw),
  },
};

export const HEAT_DATA = BUNDLED.historical;
export const LIVE_DATA = BUNDLED.live;

export const DATASETS: Record<DatasetKey, { data: HeatData; label: string; sub: string }> = {
  historical: {
    data: BUNDLED.historical,
    label: DATASET_META.historical.label,
    sub: DATASET_META.historical.sub,
  },
  live: {
    data: BUNDLED.live,
    label: DATASET_META.live.label,
    sub: DATASET_META.live.sub,
  },
};

async function getJson(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} — ${url}`);
  }
  return response.json();
}

export async function fetchDataset(key: DatasetKey): Promise<HeatData> {
  const base = `${API_BASE}/${ROUTE[key]}`;
  const [meta, hexes, hourly, city, personas, advisory, insights] =
    await Promise.all([
      getJson(`${base}/meta`),
      getJson(`${base}/map`),
      getJson(`${base}/hourly`),
      getJson(`${base}/summary`),
      getJson(`${base}/personas`),
      getJson(`${base}/advisory`),
      getJson(`${base}/insights`),
    ]);

  return { meta, hexes, hourly, city, personas, advisory, insights };
}
