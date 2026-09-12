# Implementation Plan
## HeatLens — what is built, and what is left

**Repo:** `C:\Users\HP\sih-heat` · **Tests:** **323 passing** · **Backend:** complete · **Frontend:** built · **Live forecast:** running
**Go/no-go verdict:** PROCEED — heat-stress spread across the city is **3.43 °C** against a 3.0 °C threshold, a margin of 0.43 °C, now computed from **measured satellite surface temperature** rather than an assumed amplitude
**Name:** HeatLens. The Python package stays `heatstress` — see [`DECISIONS.md`](DECISIONS.md) D18

> **How to read this.** §0 is the scorecard against the competition requirements. §1–§4 are what exists today. §5 is the work now in progress. §6 is the path to production. §7 records the findings that changed the design — including the mistakes. Technical terms are defined in the glossary in `PRD.md` Part III.

---

## 0 · Requirement coverage

**The problem statement comes first.** Its clauses are numbered PS-1 to PS-13 in `PRD.md` §1, which holds the authoritative status. This table is the build view: what is shipped, what is in progress, what is left.

| # | Problem statement clause | Built | What is left |
|---|---|---|---|
| PS-1 | Heat-stress index from temperature + humidity + wind + radiation | ✅ Phase 1 | — |
| PS-2 | WBGT / UTCI / Heat Index, not temperature alone | ✅ Phase 1 — all three, each validated and cross-checked | — |
| PS-3 | Automated **Mortality Risk Index** | ⚠️ Phase 3 — the index runs end to end, **uncalibrated by design** | Needs PS-4. Read `PRD.md` §3.1 before changing this |
| PS-4 | Historical public health data | ⬜ | Institutional access (IHIP / 108 EMRI / CRS). The `calibrate()` connection point is built and tested |
| PS-5 | Demographics — elderly / outdoor-worker density | ⚠️ Phase 3 placeholder → 🚧 Phase 5E adds total population | **Age breakdown still missing** — FR-6a: WorldPop age-sex data or Census 2011 ward tables |
| PS-6 | Localized weather data | ✅ Phase 2 + Phase 4 | — |
| PS-7 | Spikes **3–5 days ahead** | ✅ Phase 4 — **6-day horizon**, a day of margin over the requirement | Death counts blocked on PS-4; probability ranges are `[V1]` |
| PS-8 | High-resolution, hyper-local (zone / ward) | ✅ Phase 2 — 392 zones at 0.693 km², named in Phase 3; ✅ Phase 5B–5D — the pattern is now **measured** from satellite at 1 km | Landsat at 30 m (`--source gee`) needs Earth Engine sign-in; ward roll-up is `[V1]` |
| PS-9 | Dynamic colour-coded map dashboard | ✅ §4.1 | The wifi-off test is still unticked (§4.1 item 10) |
| PS-10 | Actionable automated advisories | ✅ Phase 3 | Native-speaker review of the Hindi/Gujarati text (§4.3 item 2) |
| PS-11 | **API** able to push SMS/WhatsApp alerts | ⚠️ Phase 4 — API built (26 routes), CAP message valid | **The send is deliberately switched off.** One connector behind an interface that exists. `PRD.md` §3.2 |
| PS-12 | Triggers: cooling centres · power grid · work hours | ⚠️ Work hours ✅ Phase 1+3 | Cooling centres 🚧 Phase 5F; **power grid ⬜ not started** (FR-21); rules engine `[V1]` |
| PS-13 | Serve municipal / health / disaster authorities | ✅ §4.1 | One phone call to a real health officer (§4.3 item 5) |

**Score: 7 of 13 fully built, 5 partial, 1 not started.** Three of the five partials — the lead time, the API, and the work-hour trigger — are built and were simply undersold in earlier drafts. What is genuinely open reduces to **absolute death figures** (a data-access problem, `PRD.md` §3.1), **age-specific population** (a dataset swap, FR-6a), and **grid load** (FR-21, not started).

---

## 1. The strategy: build something that could have failed

This project is **an experiment, not a small product.** It exists to answer one load-bearing question:

> Does heat stress actually vary meaningfully *within* a single city?

If the answer were no, then "hyperlocal warnings" would be a false premise and no amount of good engineering would fix it. Everything else — the map, an API, alerting — is work whose outcome was never in doubt, so it de-risks nothing.

So the build ends in a **go/no-go test with thresholds written down in advance**, before any screen was designed:

| Spread measured | Verdict | What we would do |
|---|---|---|
| 3 °C or more | The premise holds | Geography is the story; lead with the map |
| 1.5–3 °C | Real but modest | Lead with humidity and physiology instead |
| Under 1.5 °C | Premise is weak | Change direction: *same place, different bodies* |

**The result was 3.88 °C on UTCI → PROCEED**, on the assumed-amplitude method. It has since been **re-run on measured satellite temperature and still passes, at 3.43 °C** — the premise survived having its most flattering assumption removed.

**But it is no longer robust across the whole plausible range, and that must be said whenever the verdict is quoted.** Under the old method the gate passed everywhere in the literature range, so the verdict depended on no parameter choice. With the measured anomaly it depends on `alpha`:

| `alpha` | air-temp spread | UTCI spread | verdict |
|---|---|---|---|
| 0.30 | 2.01 °C | 2.57 °C | **MARGINAL** |
| 0.35 | 2.35 °C | 3.00 °C | MARGINAL (on the threshold) |
| **0.40** | **2.68 °C** | **3.43 °C** | **PROCEED** ← config |
| 0.45 | 3.02 °C | 3.86 °C | PROCEED |
| 0.50 | 3.35 °C | 4.29 °C | PROCEED |

PROCEED holds for roughly the upper two thirds of the declared `alpha_range` and fails below about 0.35. `tests/test_kill_gate.py` pins this so it cannot be quietly forgotten. **Present the alpha sweep alongside the verdict, exactly as the amplitude sweep was presented before.** Fixing this needs ground air-temperature stations across the city — see §7.16.

That same discipline is now being applied a second time: **Phase 5 writes the fitted model's pass mark into the config file before the model is fitted** (`min_spatial_cv_r2: 0.25`), and honours it either way. A threshold set in advance is the only kind that means anything.

---

## 2. What was built

### Phase 0 — Environment
| Task | Status | Note |
|---|---|---|
| Find a workable repo location | ✅ | `D:\S I H 2 6 0 8 3` is read-only at the filesystem level; moved to `C:\Users\HP\sih-heat` |
| Python 3.12 environment and dependencies | ✅ | `numpy`, `pandas`, `h3`, `thermofeel`, `requests`, `pyyaml`, `pytest`, `fastapi`, `uvicorn`, `earthengine-api` |

### Phase 1 — The physics core
| Task | Status | How it was validated |
|---|---|---|
| `psychro.py` — humidity maths | ✅ | Saturation vapour pressure within 0.017 % of steam tables at 100 °C; wet bulb hits its published worked example exactly (20 °C / 50 % → 13.70 °C) |
| `solar.py` — sun position, direct/diffuse split | ✅ | Declination checked at equinoxes and solstices; solar noon checked for Ahmedabad |
| `thermal.py` — Heat Index, WBGT, UTCI, radiant temperature | ✅ | Heat Index matches the NOAA chart within 0.4 °F; our radiant temperature and `thermofeel`'s agree to **0.005 °C** |
| `physiology.py` — ISO 7243 + ACGIH | ✅ | Limits and work/rest thresholds checked against the published tables |
| Test suite | ✅ | **323 tests** collected and passing |

### Phase 2 — Data and geography
| Task | Status | Note |
|---|---|---|
| `sources/openmeteo.py` | ✅ | Past archive and forecast, cached to disk, wind units asserted (m/s, not the km/h default) |
| `sources/osm.py` | ✅ | Overpass client with tiling, backoff, endpoint rotation, per-tile caching and percentile scaling |
| `spatial.py` — zone grid and heat offset | ✅ | 392 zones of 0.693 km² each; the bounding box is ~16.6 × 16.4 km ≈ 272 km², which the grid matches |
| Real Ahmedabad city shape | ✅ | All 32 tile queries fetched. **Caveat: the buildings layer is 0 in every zone — see §7.8** |

### Phase 3 — Risk and delivery
| Task | Status | Note |
|---|---|---|
| `vulnerability.py` | ✅ | A declared placeholder; the interface is the real deliverable |
| `risk.py` | ✅ | Dose-response machinery with a `calibrate()` connection point; uncalibrated by design |
| `advisory.py` | ✅ | CAP 1.2 XML validates; every alert marked `Exercise` |
| `insight.py` | ✅ | Cause attribution, three what-if scenarios, recommended actions, and an explicit list of what is deliberately not offered |
| Pipeline scripts 02/04/05/06 | ✅ | A full run takes about 7 seconds when cached |
| Static web files | ✅ | 7 files, ~520 KB, opens from a local file with no network |

### Phase 4 — Live mode, API, automation and deploy `[L]`
*Built and running. This section exists because it was previously undocumented here.*

| Task | Status | Note |
|---|---|---|
| `live.py` — live forecast orchestration | ✅ | Refresh loop, freshness policy (refetch if older than 15 min), a lock so two processes cannot compute at once, **an atomic seven-file publish with the metadata file written last**, and the `PAYLOAD_FILES` contract. Largest module in the package at 26 KB |
| `scripts/07_live.py`, `08_live_scheduler.py` | ✅ | A one-shot refresh and a local 5-minute scheduler. The scheduler and the API share `refresh_once` under a lock, so exactly one of them computes per cycle and the other reads what it wrote |
| `api/main.py` — FastAPI | ✅ | Background refresh task; the cached payload is replaced in a single assignment, so a request always sees one complete payload rather than a mix of old and new; falls back to reading from disk |
| Second data folder `web/data/live/` | ✅ | The same seven files as the historical folder. **Must be baked in the same pass as `web/data/`** or the two dataset tabs disagree — this happened once and is recorded in `live.py`'s docstring |
| `.github/workflows/refresh-live.yml` | ✅ | Every 6 hours: run the tests → refresh the forecast → `npm ci && npm run build` → commit the new data → deploy to GitHub Pages. **The tests gate the publish**: if a reference value has drifted, nothing ships |
| Offline guarantee preserved | ✅ | The job republishes; it does not make the page depend on a network. Data stays compiled into the bundle |

**Two rules worth writing down.** The FastAPI service must never become something the demo depends on ([`DECISIONS.md`](DECISIONS.md) D16), and Earth Engine must never initialise at import time, or the 6-hourly job fails when it runs the tests before anything else.

---

## 3. How to run it

```powershell
cd C:\Users\HP\sih-heat

.\.venv\Scripts\python.exe -m pytest                                    # 323 tests

.\.venv\Scripts\python.exe scripts\02_urban_form.py      config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\04_compute_indices.py config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\05_kill_gate.py       config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\06_bake_web.py        config\ahmedabad.yaml
.\.venv\Scripts\python.exe scripts\07_live.py            config\ahmedabad.yaml
```

Always use `.\.venv\Scripts\python.exe`, never bare `python` — the interpreter on PATH is a different environment without the dependencies.

Step 02 is safe to re-run. Every Overpass response is cached per tile, so an interrupted or partly failed run resumes and retries only the gaps. A cold run on a new city takes 30–60 minutes because of Overpass rate limits; a warm run is instant.

**Re-baking data also requires `npm run build`** in `frontend/`, because the data is compiled into the page rather than fetched (§4.1).

---

## 4. What is left in the existing scope

### 4.1 Frontend — BUILT

React + TypeScript + Vite in `frontend/`. The production build is a single self-contained `index.html` of **1,765,926 bytes (1.77 MB, 348 KB gzipped)** with the data compiled in — 1.08 MB of that is the fourteen baked payloads. The build is byte-reproducible: `npm run build` reproduces the committed `HeatLens-dashboard.html` exactly (see `.gitattributes`, which stops `core.autocrlf` from rewriting it on checkout).

> **Check for a stray `frontend/.env.local` before building the deliverable.** `VITE_API_BASE_URL` is read at build time and the API origin is compiled into the bundle, so a leftover dev override silently ships a page that points at the wrong port. It is gitignored, so nothing warns you. The shipped bundle must contain `localhost:8000` and nothing else — `grep -o 'localhost:[0-9]*' HeatLens-dashboard.html | sort -u`.

| # | Component | Status |
|---|---|---|
| 1 | SVG zone map, 4 layers, 24-hour slider, zoom and pan, keyboard-navigable | done |
| 2 | Zone detail — indices, city-shape causes, per-person verdict | done |
| 3 | Index-disagreement panel (WBGT ×0.46 vs UTCI ×1.29) | done |
| 4 | Night-recovery chart | done |
| 5 | Safe-work-window grid | done |
| 6 | Advisory and CAP payload, with unchecked-translation badges | done |
| 7 | Provenance panel — 7 layers, 3 flagged as not measured | done |
| 8 | What-if scenarios panel (shift hours · shade · greening) | done — plus a plain-English **Ask a what-if** box over a pre-baked grid, answering offline |
| 9 | Live / historical dataset switch | done |
| 10 | **Open the built page from a local file with wifi off** | **Pre-flight done, human tick still owed.** The bundle was audited and it has nothing left to fetch: 0 `<script src>`, 0 `<link>`, 0 `<img>`, 0 `<iframe>`, 0 `new Worker`, 0 service-worker registration, 0 `localStorage`/`indexedDB` (the two `serviceworker` string hits are literals in React's `preinitModule` switch, not a registration). Every `http(s)` URL in the file is an XML namespace, a React/Redux error-message URL, or `localhost:8000` — the enhancement layer, behind a 3 s timeout that degrades to the baked floor. Rendered from the built artifact with 0 console errors and 1 network request (the document). **What is still owed is the literal act: double-click the file in Chrome with wifi off and confirm.** |
| 11 | Screen-recorded backup video | TODO — live demos die |

**Two decisions worth knowing about** *(a third, the MapLibre removal, has been promoted to [`DECISIONS.md`](DECISIONS.md) D17, because it is an architectural fact rather than a frontend note)*:

- **The data is compiled into the bundle, not fetched.** Browsers block both `fetch()` and module scripts for pages opened from a local file. So re-baking data also requires `npm run build`. Anything Phase 5F adds must respect this — which is why the scenario sliders snap to a **pre-baked grid** instead of calling an API.
- **The colour scale has an explicit mode switch.** A fixed range is honest across hours but flattens the city at peak; a per-hour range reveals the pattern but is not comparable between hours. Both ship, and the legend always states which one is active.

### 4.2 Chennai — the humid comparison, and a prediction we got wrong

Ahmedabad 2010 was *dry* heat. **Live mode has since supplied a humid period for the same city**, so Chennai is no longer needed to demonstrate the humid case — it is now only a portability demonstration, and correspondingly lower priority. The pipeline is city-agnostic, so it remains a config file plus a download:

| # | Task | Estimate |
|---|---|---|
| 1 | `config/chennai.yaml` — bounding box, centre, humid heatwave dates | 20 min |
| 2 | Run steps 02/04/05/06 (the cold Overpass download dominates) | 30–60 min |
| 3 | Check that the WBGT/UTCI ordering **flips** compared with Ahmedabad | 20 min |

**We made that prediction, tested it, and it was WRONG — which turned out to be a better result.** A live September forecast for Ahmedabad (63 % average humidity, 26–35 °C) was run through the same pipeline as the dry May 2010 event (14 % humidity, 45 °C):

| | May 2010, dry | September forecast, humid |
|---|---|---|
| air temperature spread | 3.00 °C | 3.00 °C |
| WBGT spread | 1.39 °C (×0.46) | 1.38 °C (**×0.46**) |
| UTCI spread | 3.88 °C (×1.29) | 3.98 °C (**×1.33**) |

The shrinking effect **did not move with humidity**. So the mechanism is not humidity-dependent as we predicted. It comes from holding vapour pressure constant while temperature varies across zones, and the wet-bulb response to that is roughly the same across this whole range.

**Why this is the better outcome:** "use UTCI, not WBGT, for the within-city map" now holds in *both* dry and humid conditions, rather than being specific to one event. A single-city observation became a general finding — and it is one we can show we predicted incorrectly and then corrected, which is worth more than a guess that happened to be right.

### 4.3 Before any pitch

| # | Task | Why |
|---|---|---|
| 1 | **Open the built page from a local file with wifi off** | It is M4, it is NFR-1, and it is still unticked. The bundle has been audited clean and renders with 0 console errors (§4.1 item 10) — what remains is performing the act, not investigating it |
| 2 | **Native-speaker review of the Hindi and Gujarati text** | Machine-composed; an early draft contained a Lao character inside the Gujarati |
| 3 | Check the May 2010 death toll and the Heat Action Plan evaluation against original sources | Judges verify numbers |
| 4 | Source real dose-response coefficients, or present risk as strictly relative | Currently published defaults |
| 5 | Make one phone call to a municipal health officer — *"if you knew four days ahead, what would you do differently?"* | Answers R4, gives you a quotable line, costs nothing to build |

---

## 5. Phase 5 — satellite temperature, a fitted model, population, what-if 🚧

The work now in progress. Ordered so that **the highest-honesty work ships first and depends on no external service**: if Earth Engine fails, 5A still leaves the repository strictly more truthful than it was.

| Phase | Work | Estimate | Depends on |
|---|---|---|---|
| **5A ✅** | **Truth in the repo, and a guard on the verdict.** Correct the false scipy claim everywhere, fix the test count, settle on one product name, surface the buildings-are-zero defect in code and in the output, pull the go/no-go logic out of `05_kill_gate.py` into a testable function, and add `tests/test_kill_gate.py` | 2–3 h | nothing |
| **5B ✅** | **Satellite export — shipping on MODIS; Landsat path written, waiting on one browser sign-in.** `sources/gee.py` + `scripts/01_satellite_lst.py`: Landsat 8/9 thermal band (plus greenness and built-up indices), population and built-surface, and a MODIS Aqua sanity check at the 15 coarse blocks. Output `data/processed/satellite_ahmedabad.json` (~80 KB, committed) | 3–5 h | 5A · Earth Engine |
| **5C** | **The fitted model.** `downscale.py`: Ridge on 6 inputs, tested on held-out geographic blocks, 90 % conformal intervals, and four comparison baselines — including **the existing hand-chosen weights scored against the real satellite measurement**. `scripts/11_fit_downscaler.py` prints a metrics table ending in a verdict against the pass mark | 3–4 h | 5B |
| **5D ✅** | **Wire it in — the headline result.** `scripts/12_downscaled_offsets.py` writes a superset data file; a three-level file resolver; re-run 04→05→06→07; **re-bake both data folders**; regenerate the deck and case-study maps *inside this phase* | 2–3 h | 5C passing its own test |
| **5E** | **Population exposure.** Add a population-backed vulnerability surface alongside — not replacing — the placeholder; split the provenance row in two; allow exactly one narrowly-defined, checkable population statistic and keep refusing the rest | 2–3 h | 5B |
| **5F** | **Finish what-if.** Model-based greening, population-weighted outcomes, a **pre-baked** 48-row scenario grid so sliders work offline, and cooling-centre placement (`siting.py`, FR-15) | 2–3 h | 5C, 5E |
| **5G** | **Chatbot (FR-23)** — a tool-calling agent over the project's own numbers and documents, with a numeric guard that makes inventing a figure structurally impossible rather than merely discouraged. English text only in the MVP; retrieval and multilingual/voice are upside. **Design in §5.4** | ~13 h | 5A–5F for its data |
| **5H** | **Documentation.** This file, the PRD, the architecture doc, and a new `docs/DECISIONS.md` | 2–3 h | continuous |

**Already done out of 5A** (in the honesty pass that produced this document): the false scipy claim corrected in `README.md` and in `physiology.py`, `solar.py`, `sources/osm.py`, `vulnerability.py`; the test count corrected everywhere including `docs/deck/build.py`; the product name unified to HeatLens across the API, `server.py` and the frontend; and a real bug fixed in the what-if scenario (§7.10).

**5A is now closed.** `killgate.py` holds `verdict()`, `05_kill_gate.py` only prints what it returns, and `tests/test_kill_gate.py` (16 tests) pins the shipped numbers — 3.88 °C on UTCI, margin +0.88 °C — against the *committed* arrays, so a change to the offset that would flip the verdict now fails a test. `UrbanIntensity.coverage()` and `format_coverage()` report the buildings defect in the pipeline's own output rather than in a docstring: on the shipped surface `built` is dead, and **0.75 of the formula's 1.30 total weight is actually in play.**

**5B and 5D are done, by a route the plan did not anticipate.** Earth Engine needs a browser sign-in that no script can perform, so rather than leave the pattern assumed indefinitely, the satellite path now ships on **MODIS Aqua via ORNL DAAC**, which serves land-surface temperature subsets as JSON with no registration, no API key and no approval wait — the same property that made Overpass and Open-Meteo the right calls in the first place (D2). What shipped:

| | |
|---|---|
| Instrument | MODIS Aqua `MYD11A2`, day (13:30) **and night (01:30)** — the day overpass is within half an hour of the 14:00 IST focus hour |
| Period | 21 eight-day composites, April–May 2023–2025 |
| Coverage | **381 of 392 zones measured** (97.2 %); 11 edge zones filled from measured neighbours and labelled `filled_neighbour` |
| Resolution | 926 m pixels → 295 distinct pixels behind 392 zones. Honestly blocky; no interpolation invented |
| Cross-check | **Terra `MOD11A2` agrees at 0.946** rank correlation over the 15 coarse blocks — a different satellite on a different orbit |
| Verdict | **PROCEED at 3.43 °C** (was 3.88 °C assumed), margin +0.43 °C |

`sources/gee.py` and `--source gee` remain in place and tested: authorise Earth Engine and the same pipeline picks up Landsat at 30 m with no other change. **The 1 km limitation is the reason to still do it.**

**~~Minimum credible plan~~ — 5A, 5B and 5D are shipped.** What remains, in value order: **5C** (the Ridge fit, for error bars and a real greening simulation — the observation already supplies the operational number, so this is no longer on the critical path), **5E** (population), **5F** (cooling-centre siting — the what-if half is now shipped), **5G** (chatbot, the biggest demo win and the largest block of time).

### 5.1 Four rules this phase must not break

1. **Guard before you change.** `tests/test_kill_gate.py` lands in 5A, *before* anything touches the temperature offset. **This worked exactly as intended:** when 5D swapped in the measured pattern, the guard failed on the quoted margin (0.88 → 0.43 °C) while the `PROCEED` verdict itself held. The number was then updated deliberately, with the reason recorded in the test's own docstring, instead of drifting away from every document that quotes it.
2. **The operational number comes from the *observation*, not the model's prediction.** Predictions pull toward the average, which would shrink the spread by roughly the square root of the fit quality — and that spread is exactly what the go/no-go test measures. The model fills gaps, supplies error bars, and powers the what-if simulator. (`ARCHITECTURE.md` §6 D14.)
3. **The model's pass mark is honoured in both directions.** `min_spatial_cv_r2: 0.25` goes in the config before fitting. If the model misses it, 5D refuses to write, the existing method stays, and the number is published anyway.
4. **The offline guarantee is untouchable.** No new network call at runtime, no reimplementation of the physics in TypeScript, scenario grids pre-baked rather than computed live, and the chat panel hides itself when the backend is unreachable.

### 5.2 Config additions (`config/ahmedabad.yaml`)

Three of these keys — `alpha`, `alpha_range` and `lst_composite` — **already exist in the file and are read by no code at all**: a complete satellite specification written and never connected. Phase 5 switches them on and adds the rest.

```yaml
urban_heat:
  mode: lst                       # lst | osm_composite
  alpha: 0.40                     # NOW LIVE (was dead config)
  alpha_range: [0.30, 0.50]       # NOW LIVE -- the new sensitivity sweep
  lst_composite:
    years: [2023, 2024, 2025]
    months: [4, 5]
    max_cloud_cover_pct: 10
    min_valid_px_per_cell: 200    # NEW  ~25% of the ~800 30 m pixels in a zone
    min_scenes: 5                 # NEW  below this, abort the export
  downscale:                      # NEW
    features: [ndvi, ndbi, built_s, roads, green, water]
    ridge_lambda_grid: [0.01, 0.1, 1.0, 10.0, 100.0]
    cv_group_resolution: 6        # 15 groups on the real grid, sizes 2-49
    cv_folds: 5
    conformal_alpha: 0.10
    min_spatial_cv_r2: 0.25       # the pass mark, declared BEFORE fitting
population:                       # NEW
  source: JRC/GHSL/P2023A/GHS_POP
  epoch: 2020
siting:                           # NEW
  walk_rings: 1                   # 7 zones, about 0.9 km — a short walk in extreme heat
  n_centres: 12
```

**No new dependencies for 5A–5F.** `earthengine-api` is in `requirements.txt` for 5B (it was pruned once as unused and put back deliberately -- do not prune it again while Phase 5 is open); the model is numpy plus the hex library. LightGBM is benchmarked in a throwaway environment and **not added** — the 6-hourly job installs dependencies on every run.

### 5.3 Phase checks

| Phase | What must be true before moving on |
|---|---|
| 5A | Tests green; `tests/test_kill_gate.py` passes against the *committed* stored arrays before any change to the offset |
| 5B | `01_satellite_lst.py` writes its output with at least 5 usable scenes and 90 % zone coverage; **re-running it makes zero network calls** |
| 5C | The metrics table prints; held-out score at least 0.25; error bars contain the truth within 5 points of 90 %; the naive-versus-honest gap reported; the hand-weighted baseline number recorded |
| 5D | 04→05→06→07 re-runs clean; verdict still PROCEED (or the failure reported with **both** methods shown); both data folders re-baked; `npm run build` succeeds; **the built page opened from disk with wifi off renders the full dashboard** |
| 5E | Provenance has 8 rows; the vulnerability row still says `NOT FITTED`; the placeholder still reports `is_placeholder=True`; the population statistic refuses to run without a stated threshold |
| 5F | Siting coverage never decreases as you add centres; zero centres covers zero people; enough centres covers everyone; the sliders work offline |
| 5G | A grounded answer with a visible trace of which numbers it used; "how many people are at risk?" returns the *narrowed* statistic with its caveat, not the old blanket refusal and not a casualty figure; "is this validated?" returns "cross-checked against held-out satellite measurements" and never "validated" |
| 5H | No file claims scipy is blocked; no file says 135 tests; one product name; `docs/DECISIONS.md` records D2 as **superseded**, not deleted |

The suite was expected to grow from 181 to roughly 200. It is at **272**: 5A +16 (the kill-gate guard), 5B +31 (the Earth Engine path), the MODIS path +35, plus the coverage report. The satellite work carried far more silently-wrong-answer surface than estimated — units, pixel geolocation, quality flags paired to the wrong date, and provenance — and that is where most of the new tests went.

---

### 5.4 Phase 5G — the chatbot, in full

The single largest block in Phase 5 and the biggest demo win, so it is specified
here rather than left as a table row. **It is a tool-calling agent with hybrid
retrieval, not a chat wrapper over a prompt.** The distinction is the whole
design: the agent may only state numbers that a tool handed it.

**Why this shape.** Every other part of this project can be checked — two
independent physics implementations agreeing to 0.005 °C, a kill gate declared
before it was measured, a model pass mark written into config before fitting. A
chatbot that answers from a language model's recall would be the one component
nobody can audit, bolted onto a system whose entire argument is auditability. So
the agent is built the other way round: **the model chooses tools and writes
prose; it never supplies a figure.**

**Three guards, in order of importance.**

1. **Numeric guard.** Every number in an answer must be traceable to a tool
   return. Any figure that is not is rejected before the answer is emitted —
   this is a post-check on the generated text, not an instruction in the prompt,
   because an instruction is a request and a check is a guarantee.
2. **Refusal table.** An explicit list of questions the data cannot honestly
   answer: casualty or death counts (`ExposureResponse.is_calibrated` is
   `False`), "is this validated?" (the honest answer is "cross-checked against
   held-out satellite observations", never "validated"), and per-household or
   per-person claims. **The table is versioned against the phases**: when 5E
   lands real population, the bot must stop refusing headcounts on a premise
   that is no longer true — and must keep refusing the ones that are still
   fabrication. A stale refusal is as dishonest as a stale claim.
3. **Verbatim advisory substitution.** Public-health instructions are returned
   exactly as `advisory.py` composed them. A paraphrased instruction is a new
   instruction that nobody reviewed, and the Hindi and Gujarati strings are not
   yet native-speaker verified even in their original form.

**Retrieval.** Hybrid — structured lookups into the baked payloads for anything
numeric, and dense retrieval over the project's own markdown for "why" and "how"
questions. Embeddings come from `model2vec` (`minishlab/potion-base-8M`, ~30 MB
static, no GPU, no inference server), so the index builds in seconds and neither
the corpus nor the question leaves the machine. `scripts/09` builds the index;
`scripts/10` is the answer-quality eval.

**Tools.** The existing payload readers, plus four that unlock as A–F land:
`get_lst_anomaly` (measured LST with `n_valid_px` and `d_ta_source`),
`get_population_exposure` (the narrowly-defined statistic from 5E, carrying its
caveat field), `get_model_card` (spatial-CV metrics and conformal coverage), and
`run_siting`. The parameterised shade/greening/warming scenario tools need the
`insights["frame"]` emit — per-cell `ta/rh/wind/ghi` at the focus hour, ~20 KB,
placed **inside** `insights` so `PAYLOAD_FILES` and the frontend types are
untouched. Phase 5F wants the same emit, so it is built once.

**Wiring.** `api/chat.py` exposes `APIRouter(prefix="/api/chat")`; `api/main.py`
gains one import and one `include_router`. Nothing else in the API changes.

**The offline rule is not negotiable.** D16 says the API may never become a
demo dependency, so the chat panel **hides itself** when `/api/health` does not
answer. A chat box that cannot reach its tools cannot cite anything, and a
citation-less answer from this system would be worse than no answer.

**New dependencies:** `python-dotenv` and `model2vec`. Nothing else.

**Gate.** `curl -X POST localhost:8000/api/chat` returns a grounded answer with
a visible tool trace; *"how many people are at risk?"* returns the **narrowed**
statistic with its caveat — not the old blanket refusal, and not a casualty
figure; *"is this model validated?"* returns "cross-validated against held-out
satellite observations" and never the bare word "validated".

---

## 6. The path to production

The prototype was built so that production is a **substitution, not a rewrite**.

| Prototype | Production | The plug-in point | Status |
|---|---|---|---|
| Replay of one past event | A live forecast | New source module; physics unchanged | ✅ **built** (Phase 4) |
| Static files only | A FastAPI service alongside them | The data contract is already frozen | ✅ **built** (Phase 4) — database still future |
| Notebook-grade UI | React dashboard, one offline-capable file | — | ✅ **built** |
| OpenStreetMap city shape | Satellite temperature plus a fitted model | `spatial.UrbanFormSource` interface | 🚧 Phase 5B–5D |
| An assumed 3 °C | A measured pattern and one assumed number (`alpha`) | The figure is already isolated in config | 🚧 Phase 5D |
| Placeholder exposure | Real residential population | `vulnerability.VulnerabilitySource` interface | 🚧 Phase 5E |
| — | Cooling-centre placement / what-if planner | `insight.py` scenarios already in place | 🚧 Phase 5F |
| One forecast | A **range** of possible outcomes | Same source module | ⬜ `[V1]` |
| Placeholder vulnerability | Census 2011 + NFHS-5 ward index | `vulnerability.VulnerabilitySource` interface | ⬜ `[V1]` |
| Age-blind population | **Elderly density per zone** (FR-6a, PS-5) | WorldPop age-sex data or Census ward age tables; same percentile scaling | ⬜ `[V1]` |
| Published dose-response | Fitted on real health records | `risk.ExposureResponse.calibrate()` | ⬜ `[V1]` — **not attempted; no data** |
| Equal-area zones | Official ward boundaries | The grouping code is boundary-agnostic | ⬜ `[V1]` |
| Rendered advisory | CAP → NDMA SACHET + SMS / WhatsApp / voice | The CAP message is valid; sending deliberately unwired | ⬜ `[V1]` |
| — | **Zone-level grid load** (FR-21, PS-12) | Cooling-load proxy over the forecast; no plug-in point yet | ⬜ `[V1]` — **not started** |
| — | Indoor and night-time model by roof type | Census roof-material tables | ⬜ `[V1]` |
| — | Heat action rules engine | — | ⬜ `[V1]` |

**The highest-value remaining production item is the indoor/night-time model.** The Ahmedabad finding — six consecutive nights above 26.7 °C with no chance for a body to recover — is the strongest evidence in the whole project, and it is currently inferred from *outdoor* air temperature. Modelling indoor temperature by roof material (tin, asbestos, concrete, tiled), which Census 2011 provides at ward level, would make it far stronger, and it is something essentially no competing team will attempt.

**The longest lead time is health-outcome data.** Institutional requests should go out immediately regardless of build order. Even a rejection letter is evidence of having pursued the real path instead of inventing numbers.

---

## 7. What we learned while building

> **Findings 12–15 were added after the satellite data landed, and are the strongest results in this list.**

Recorded because each of these changed the design, and several are presentable results in their own right.

1. **May 2010 Ahmedabad was dry heat, at 13–16 % humidity.** Humidity was not the killer there. The correct thesis is that temperature alone misleads *in both directions*.
2. **The nights were the killer.** Six consecutive nights with no drop below 26.7 °C, and UTCI still at 33.1 °C at midnight. Daytime-maximum warnings cannot see this at all.
3. **WBGT shrinks within-city variation (×0.46); UTCI magnifies it (×1.29).** A hotter zone is a drier zone. Later shown in §4.2 to be **independent of humidity**, which turned an event-specific recommendation into a general one.
4. **An outdoor construction worker had zero full-capacity working hours** on 21 May 2010, with **eight** consecutive hours (10:00–17:00) at zero safe minutes for every person type. Earlier notes said nine; the computed value is eight, because at 18:00 a delivery rider regains 15 minutes per hour. Directly actionable, straight from published occupational standards.
5. **CORRECTED — the scipy claim was false, and has now been fixed everywhere.** An earlier finding recorded that Windows Application Control blocked `scipy.optimize`, which removed the ISO 7933 model. On this machine **`scipy 1.18.1`, `scipy.optimize` and `pythermalcomfort 4.4.2` all import cleanly** (as do `earthengine-api 1.7.41` and `h3 4.5.0`; `sklearn`, `lightgbm` and `statsmodels` are simply not installed, not blocked). The claim had spread to seven places across the source and docs; all seven are now corrected. In `sources/osm.py` and `vulnerability.py` it was also the stated *reason* for avoiding heavyweight geospatial libraries, so the reason was **replaced** rather than deleted — Phase 5 avoids those libraries anyway, by averaging on Google's servers and fetching only numbers.
   **The `thermofeel` choice itself was right on its own merits** — it ships the full Liljegren WBGT model, which retired the simpler wet-bulb approximation entirely. Only the reason was wrong.
6. **Fixed-cap scaling flattened the city** (median score 0.975) until it was replaced with percentile scaling — which also makes the pipeline portable to another city.
7. **Overpass rejects the default `python-requests` user agent with HTTP 406**, and the number of requests rather than their size dominates its cost.
8. **The buildings layer is 0.0 in all 392 zones, so the city-shape score is road density.** The formula weights `0.55·buildings + 0.25·roads − 0.30·greenery − 0.20·water`, but buildings were switched off, so the **largest weight in the project's core formula contributes nothing**. Measured on the shipped data: correlation with roads +0.855, with water −0.778, with greenery −0.286, and greenery is non-zero in only 175 of 392 zones (mean 0.023). A layer with no coverage contributes nothing regardless of its weight — which is now to be stated in the formula's own docstring and surfaced by a coverage report. **This is the strongest single argument for measuring the pattern from satellite**, and the reason `ARCHITECTURE.md` D2 is marked superseded rather than quietly rewritten.
9. **The effective sample size is about 20–25, not 392.** The city is roughly 16 × 16 km and surface temperature stays similar over 1–3 km. Independently, grouping zones by parent hexagon gives exactly **15 groups** on this grid (sizes 2, 2, 3, 5, 15, 18, 20, 23, 24, 42, 42, 49, 49, 49, 49 — badly unbalanced, which the fold builder must handle). That number, not 392, governs how many parameters may honestly be fitted, and it is why Phase 5C chooses Ridge over boosted trees.
10. **FIXED — a real bug in the what-if simulator, found by running the tests on a stale cache.** `insight.scenario_shift_hours` asks about specific clock hours (06:00–21:00) but indexed the day's data **by list position**, silently assuming position equals hour of day. That holds for a complete midnight-to-midnight day and fails for a part-day — and a forecast window requested in UTC and read in local time has a part-day at each end. The symptom was an `IndexError` that crashed the whole live computation, and it only appeared when the committed forecast cache had aged relative to the clock. Because the 6-hourly job runs the tests *before* refreshing, a stale cache there would mean nothing publishes.
    The fix makes the function **address data by clock hour**, skip scheduled hours with no forecast rather than guessing them, and report `hours_scored` and `covers_full_shift` so a partial comparison declares itself. Six tests now pin this against fixed inputs, so they cannot pass or fail depending on the day they run — which is exactly how the original failure hid. The historical numbers are unchanged: 17.8 → 11.0 unsafe person-hours, a 38 % reduction.
11. **The go/no-go test was printed to the screen and never tested**, at a margin of 0.88 °C. The project's own verdict was unguarded. Extracting it into a testable function is the first remaining task of Phase 5, deliberately ordered before anything that changes the temperature offset.

12. **The hand-built urban-form formula barely tracked the real heat pattern: rank correlation 0.197.** This is the vindication of §7.8 and the most presentable result the project has. The shipped map was `0.55·built + 0.25·roads − 0.30·green − 0.20·water` with `built` empty in all 392 zones — road density in a trench coat. Measured against MODIS surface temperature over three pre-monsoon seasons, that index and the real thermal pattern agree at **0.197**, and **48 of 392 zones move by more than 1 °C** when the measurement replaces the guess. We were confidently colouring the wrong neighbourhoods.
13. **The premise survives losing its most flattering assumption.** The kill gate read 3.88 °C when the amplitude was an assumed 3.0 °C. On measured satellite temperature with `alpha = 0.40` it reads **3.43 °C — still PROCEED**, margin +0.43 °C. A verdict that held only while a convenient number was assumed would have been worthless. Note the direction: the assumption had been *flattering* us by about half a degree.
14. **Two independent satellites see the same city: Terra vs Aqua rank agreement 0.946.** Different spacecraft, different orbit, different overpass time (10:30 against 13:30). The OpenStreetMap formula had no way of being shown wrong at all; this pattern is checked against an instrument sharing none of its inputs, and the check is stored in the output file rather than asserted on a slide.
15. **Night is a different map from day — and this project's own thesis is that night is what kills.** The 01:30 surface anomaly spans 4.67 °C against 6.71 °C by day, over different zones: dense masonry releases stored heat all night while the bare periphery dumps it within the hour. The May 2010 deaths tracked six consecutive nights that never fell below 26.7 °C. This layer is now measured and stored per zone, and **nothing in the UI uses it yet** — the most valuable unclaimed result in the repository.
16. **Nothing in this project has ever been validated against a thermometer inside the city.** The physics is cross-checked against `thermofeel` and published tables; the satellite pattern is cross-checked against a second satellite. Neither is a check on the thing actually published: **per-zone air temperature**. The chain is `measured city weather + measured surface pattern × assumed alpha`, and `alpha` is the join between the two measured halves — the one link with no observation behind it. It cannot be fitted without ground weather stations across Ahmedabad, which do not exist in this repository. Since the go/no-go verdict now depends on `alpha` (§1), **a handful of cheap logging thermometers in a few contrasting zones for one hot week is now the single highest-value piece of fieldwork available to this project** — it would convert the last assumption into a measurement and make the verdict parameter-free again.
