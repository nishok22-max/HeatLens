# Heat Stress Early Warning — backend

Human thermal stress and heat-health risk at neighbourhood scale, for Indian
cities. SIH problem statement: *Extreme Heatwave Early Warning and Human Thermal
Stress Index*.

**Repo location:** `C:\Users\HP\sih-heat`
(not `D:\S I H 2 6 0 8 3` — that path is read-only at the NTFS level: `BUILTIN\Users`
has `(RX)` only. To use it instead, run elevated:
`icacls "D:\S I H 2 6 0 8 3" /grant "$env:USERNAME:(OI)(CI)F" /T`)

---

## Quick start

Everything below assumes you are in the repo root:

```powershell
cd C:\Users\HP\sih-heat
```

### Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Expect **181 passed**. This is the credibility artefact — it validates the
physics against published reference values (NOAA Heat Index chart, ISO 7243
limits, Stull's own worked example) *and* cross-checks our from-scratch
implementations against `thermofeel`, ECMWF's operational library.

### Run the full pipeline

```powershell
.\.venv\Scripts\python.exe scripts\02_urban_form.py config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\04_compute_indices.py config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\05_kill_gate.py config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\06_bake_web.py config\ahmedabad.yaml
```

**~7 seconds total** once the network responses are cached (they are — see
`data/raw/`). A cold run takes 30–60 min because Overpass is heavily rate-limited.

---

## What each step does

| step | script | does | writes |
|---|---|---|---|
| 2 | `02_urban_form.py` | H3 grid over the city; fetches roads / green / water from OpenStreetMap; derives per-cell temperature offsets | `data/processed/urban_form_<city>.json` |
| 4 | `04_compute_indices.py` | Applies the physics graph to every cell-hour: WBGT (Liljegren), UTCI, Heat Index, risk | `data/processed/indices_<city>.npz` |
| 5 | `05_kill_gate.py` | **The decision script.** Reports intra-city spread, the WBGT-damping finding, and a sensitivity sweep over the assumed UHI amplitude | stdout only |
| 6 | `06_bake_web.py` | Bakes static assets for the frontend | `web/data/*.json`, `web/data/hexes.geojson` |

Step 2 is safe to re-run: every Overpass response is cached per tile, so a run
interrupted or partially failed resumes and only retries the gaps.

---

## Outputs the frontend reads

`web/data/` — 530 KB total, no server, no network. All seven are required:
a missing one fails the frontend build and 404s the API.

| file | size | contents |
|---|---|---|
| `hexes.geojson` | 214 KB | 392 cells with static properties |
| `hourly.json` | 267 KB | focus-day 24 h per cell |
| `city.json` | 11 KB | all 264 h city-mean + night-recovery series |
| `personas.json` | 3 KB | safe-work windows per persona |
| `advisory.json` | 3 KB | multilingual advisory + CAP 1.2 XML |
| `insights.json` | 3 KB | drivers, intervention scenarios, recommended actions |
| `meta.json` | 4 KB | provenance, kill-gate numbers, declared caveats |

Full spatial detail for one day; full temporal detail for the city aggregate.
Shipping the cross product would be ~500k numbers.

---

## Zone names

H3 identifies a cell as `8842cc6821fffff`, which nobody can act on or discuss.
`scripts/03_place_names.py` fetches OpenStreetMap's named place nodes for the
city and labels each zone with its nearest one:

```powershell
.\.venv\Scripts\python.exe scripts\03_place_names.py config\ahmedabad.yaml
```

Ahmedabad resolves to **75 distinct names** across 392 zones (Bodakdev,
Navrangpura, Maninagar, Asarwa...). The UI leads with the name and keeps the H3
code as small secondary text, and a "Find a neighbourhood" dropdown lets someone
jump straight to their own area.

**These are labels, not boundaries.** A zone called "Maninagar" is the zone
nearest the point OSM calls Maninagar — it is not the Maninagar ward. 247 of 392
zones sit within 1.2 km of their place; the rest are shown as "Zone near X" so
the looser matches are not overstated.

One Overpass query for the whole city, rather than reverse-geocoding 392
centroids one at a time — lighter, faster, and far more polite to OSM's servers.

---

## Live forecast mode

Alongside the May 2010 hindcast, the demo carries a **live forecast** for the
same city — current conditions plus about five days ahead.

```powershell
.\.venv\Scripts\python.exe scripts\07_live.py config\ahmedabad.yaml
cd frontend; npm run build
```

The frontend shows both as tabs. It exists to close two gaps: the problem
statement asks for a 3-5 day outlook, and a hindcast invites the obvious
question *"so it only works on the past?"*.

**Why it was cheap to add:** the pipeline is date-agnostic. Open-Meteo's
forecast endpoint returns the same variables, units and response shape as the
archive endpoint, so `fetch_forecast()` is a near-copy of `fetch_hourly()` and
every downstream stage — solar geometry, Liljegren WBGT, UTCI, personas, risk —
runs unchanged.

**Live does not mean more accurate.** The per-neighbourhood downscaling still
rests on the assumed urban-heat amplitude. Live input changes how *current* the
numbers are, not how *validated*. Every provenance flag stays exactly as it was.

**Keeping it fresh — every five minutes, locally.**

```powershell
# either of these refreshes web/data/live/ on a 5-minute interval
python -m uvicorn api.main:app --port 8000        # the API does it on its own
.\.venv\Scripts\python.exe scripts\08_live_scheduler.py config\ahmedabad.yaml
```

Both call one function, `heatstress.live.refresh_once`, which takes a lock:
whoever gets it computes and writes, and whoever does not reads what the winner
wrote. Running the API alone, the scheduler alone, or both is therefore correct,
and running both costs one recompute per interval rather than two. The scheduler
exists for the cases uvicorn does not cover — refreshing the baked files with the
API down, a controllable `--interval` and `--once` for testing, and being the
thing you would hand to Task Scheduler or systemd.

*Why recompute every five minutes when Open-Meteo only publishes hourly:* the
focus is **the peak stress hour ahead**, so it moves with the wall clock even
when the weather payload has not changed, and a page labelled live with a frozen
timestamp is a credibility problem. A recompute costs under a second, and the
writer skips files whose bytes did not change — a typical tick rewrites only
`meta.json`. Interval and forecast TTL are in the `live:` block of the city
config.

`.github/workflows/refresh-live.yml` still re-runs the pipeline every six hours,
commits the refreshed JSON and redeploys the page — that is what keeps the
*published* copy current for anyone who is not running the API locally.

The demo stays offline-capable either way, and this is deliberate: the baked
data is still compiled into the page as the **floor**, and the API is an overlay
on top of it. So opening `index.html` from a USB stick with wifi off shows the
last published forecast with its retrieval time on screen, never a blank map or
a spinner; and when the API *is* reachable, the page silently upgrades to live
numbers every five minutes. A failed refresh degrades to a small "not refreshing"
badge beside the timestamp rather than to an error page — the data on screen is
still the last good data.

---

## Backend API

`api/main.py` (FastAPI) is **the** backend. There is no other one.

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

| route | serves |
|---|---|
| `/api/health` | liveness probe + `live_refreshed_at`, which is what the UI badge reads |
| `/api/v1/historical/{meta,map,hourly,summary,personas,advisory,insights}` | the May 2010 hindcast |
| `/api/v1/forecast/...` | the live forecast, same seven routes |

`/api/v1/live/...` is kept as an alias for `forecast`, because the UI calls the
dataset "live" and the API namespaces it "forecast".

**The frontend does not require it.** `frontend/src/data.ts` compiles the baked
JSON into the bundle as the floor and `frontend/src/api.ts` upgrades to the API
when `/api/health` answers; when it does not, the badge flips to "Offline Mode"
and the bundled numbers stay on screen. Route names live in exactly one place
(`fetchDataset` in `data.ts`) so the two cannot drift apart.

---

## Frontend

React + TypeScript + Vite, in `frontend/`.

```powershell
cd C:\Users\HP\sih-heat\frontend
npm install
npm run dev      # development, http://localhost:5173
npm run build    # production -> frontend/dist/index.html
```

The production build is **a single self-contained `index.html`** (~1.1 MB) with
the CSS, JS and all six data files inlined. Open it directly from disk, email it,
or put it on a USB stick — no server, no network, nothing to install.

**Two things follow from that, and they are deliberate:**

1. **Re-baking the data requires a frontend rebuild.** The data is compiled in,
   not fetched. Run `06_bake_web.py`, then `npm run build`.
2. **Why inline rather than fetch:** Chromium treats a page opened from `file://`
   as an opaque origin and blocks `fetch()`, module-script loading and web
   workers. A conventional build renders blank from disk — which is exactly the
   scenario the offline requirement exists to cover. Inlining removes the whole
   class of failure.

There is **no basemap**, for the same reason: every map style fetches tiles from
a server. The hex grid covers the study area on its own, and cells with green or
water cover are outlined so parks and the Sabarmati stay recognisable. The map is
hand-rolled SVG rather than MapLibre — MapLibre v6 needs a web worker, which
cannot be constructed from `file://`.

**The colour scale has two modes, and the legend always says which is active.**
*Absolute* is a fixed domain across all 24 hours, so colours are comparable as
you scrub. *Contrast* rescales to the values present at the visible hour, which
is the only way the intra-city pattern is visible at the peak of the event.
Neither is dishonest; showing one without saying which would be.

---

## Targeting a different city

The pipeline is city-agnostic. Copy `config/ahmedabad.yaml`, change the bbox,
centre, and hindcast dates, then run steps 2/4/5/6 against the new file. Nothing
in the code is Ahmedabad-specific, and normalisation is percentile-based so
thresholds do not need retuning per city.

---

## Read this before quoting any number

`web/data/meta.json` carries a `status` on every layer. Three of them are **not**
measured:

- **UHI amplitude is ASSUMED** (3.0 °C, a literature value). The spatial
  *pattern* comes from real OpenStreetMap urban form, but the *magnitude* does
  not. Present the sensitivity sweep from step 5 alongside any spread figure.
- **Vulnerability is a declared PLACEHOLDER.** No ward-level demographics were
  obtainable, so it is a city-wide constant and does not vary between
  neighbourhoods — meaning risk variation is driven almost entirely by hazard.
- **Exposure–response is NOT CALIBRATED** to local health records. The
  coefficients are literature-shaped defaults; `risk.ExposureResponse.calibrate()`
  is the seam where real data enters.

Additionally: **the Hindi and Gujarati advisory strings are machine-composed and
unverified.** An early draft contained a Lao codepoint inside the Gujarati text.
`LANGUAGES_VERIFIED` gates them and a test asserts script integrity, but they
need a native speaker before any pitch or dispatch.

CAP output is stamped `status=Exercise`, never `Actual`.

---

## Environment notes

- Python 3.12 venv at `.venv`. The system `python` on PATH is a different
  interpreter without pip — always use `.\.venv\Scripts\python.exe`.
- **`physiology.py` uses ISO 7243 + ACGIH work/rest tables, not ISO 7933 PHS.**
  An earlier note here claimed `pythermalcomfort` could not be imported because
  Windows Application Control blocked a `scipy.optimize` DLL. That is no longer
  true — `scipy 1.18.1`, `scipy.optimize` and `pythermalcomfort 4.4.2` all import
  cleanly. The choice stands on its own merits: a lookup table has no solver to
  fail mid-demo, and work/rest allowances are what occupational hygienists
  actually sign off on.
- `thermofeel` (ECMWF) works and supplies Liljegren WBGT and the UTCI polynomial.
