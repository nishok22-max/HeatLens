# Decisions

The authoritative record of *why* this system is shaped the way it is — one
entry per decision, kept whether or not the decision survived.

**Reversals stay visible.** D2 and D3 were both overtaken by later evidence and
are marked, not deleted. A decision log you edit to hide the reversals is worth
nothing: the reason a choice was right at the time is exactly the context you
need to judge whether the reversal is right now.

`ARCHITECTURE.md` §6 carries a short summary of the load-bearing few and links
here. This file is the record.

**Status values:** `Accepted` · `Accepted 🚧` (decided, being built) ·
`Superseded by D-NN` · `Reversed`.

---

## D1 — Equal-area hexagons, not municipal wards

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

Ward boundary files are a multi-day hunt with nothing to learn from. The hex grid covers any city instantly and every zone has the same area (0.693 km²), so per-zone numbers are directly comparable — which is not true of wards, whose areas vary wildly.

---

## D2 — OpenStreetMap city shape, not satellite temperature

**Status:** Superseded by D14  ·  **Recorded:** 2026-09-01 (first commit)

Correct at the time: no registration, no approval wait, plain JSON so no heavyweight geospatial libraries, and it works for any city immediately. Satellite access has since been granted, and §2.3 shows the OpenStreetMap formula collapsed into road density — so the premise no longer holds.

---

## D3 — `thermofeel`, not `pythermalcomfort`

**Status:** Rewritten — the original reason was false  ·  **Recorded:** 2026-09-01 (first commit)

The original entry said Windows Application Control blocked a `scipy.optimize` DLL. **On this machine `scipy 1.18.1`, `scipy.optimize` and `pythermalcomfort 4.4.2` all import cleanly.** The decision stands on its own merits regardless: `thermofeel` ships the full **Liljegren** WBGT model, which is what retired assumption A2, and it is the European weather centre's operational library.

---

## D4 — ISO 7243 + ACGIH lookup tables, not the ISO 7933 differential model

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

Tables rather than an equation that has to be solved numerically: nothing can fail to converge mid-demo, and tables are what occupational hygienists actually use — so the output maps onto a decision an official can sign. *(Originally presented as a consequence of D3; it is a choice on its own merits.)*

---

## D5 — Replay a past event first, forecast second

**Status:** Accepted, extended  ·  **Recorded:** 2026-09-01 (first commit)

Forecasting is a separate problem that does not test the core premise, and replaying a real disaster you can point at is more persuasive. A live forecast has since been added alongside; the historical replay remains the validation artefact.

---

## D6 — Static files, no database

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

Every number is precomputed and never changes. Simpler, better-looking, and it cannot fail on stage.

---

## D7 — Percentile scaling, not fixed caps

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

A fixed 12 km road-length cap pinned most of central Ahmedabad to 1.0 (median 0.975), flattening the dense old city into one colour. Percentile scaling also makes the pipeline portable — an absolute threshold tuned on Ahmedabad would misscale Chennai.

---

## D8 — Carry vapour pressure between zones

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

See §2.1. Prevents an error that would have flattered our own result.

---

## D9 — CAP alerts marked `Exercise`, never `Actual`

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

A prototype must never emit something real alerting infrastructure would act on.

---

## D10 — Alert sending deliberately not wired

**Status:** Accepted  ·  **Recorded:** 2026-09-01 (first commit)

An alerting system that can fire during a demo is a hazard. The warning text and CAP message are returned as strings, for display only.

---

## D11 — Model coefficients as committed JSON, never a pickle

**Status:** Accepted 🚧  ·  **Recorded:** 2026-09-09 (honesty pass)

Pickle files break between numpy versions, cannot be read in review, and are a security hazard in a repository people clone. A 2 KB JSON file of coefficients can be diffed and audited.

---

## D12 — Ridge regression, not LightGBM or random forest

**Status:** Accepted 🚧  ·  **Recorded:** 2026-09-09 (honesty pass)

The city is about 16 × 16 km and surface temperature stays similar over 1–3 km, so the **effective** sample size is roughly 20–25 independent locations, not 392. The hex grid agrees: grouping zones by their parent hexagon gives exactly **15 groups**. Boosted trees mean thousands of parameters fitted to ~20 independent observations — a beautiful score on the data it was fitted to, a worse score on held-out geography, plus a compiled package the 6-hourly job would install every run. Random forests additionally cannot extrapolate, which breaks the portability requirement (NFR-5). Ridge is closed-form, adds no dependency, and its coefficients fit on a slide. **LightGBM is to be run once in a scratch environment as a benchmark and its held-out score quoted** — "we tried the model §8 promised and it lost at this sample size" is a stronger claim than silently downgrading.

---

## D13 — Hold out whole geographic blocks, not scattered zones

**Status:** Accepted 🚧  ·  **Recorded:** 2026-09-09 (honesty pass)

With 392 adjacent hexagons, hiding one at random leaves roughly 5 of its 6 neighbours in the training data — same roads, same park, often the same satellite pixels along the boundary. That measures how well the model fills gaps, not how well it predicts. Groups are parent hexagons: 15 groups, sizes 2 to 49, badly unbalanced, which the fold builder must handle. The naive random score is reported *alongside* the honest one; the gap between them is itself a result.

---

## D14 — Use the observed satellite measurement for the pattern; use the model only for gaps, error bars and what-if

**Status:** Accepted 🚧  ·  **Recorded:** 2026-09-09 (honesty pass)

Model predictions pull toward the average, which would shrink the city-wide spread by roughly the square root of the fit quality — and that spread is exactly what our go/no-go threshold measures. So the operational number comes from the *observation*, and the fitted model does the three jobs observation cannot: fill cloud-blanked zones, supply the error bar, and make the greening simulation a real recalculation. Supersedes D2.

---

## D15 — Use free global population data; leave vulnerability a city-wide constant

**Status:** Accepted 🚧  ·  **Recorded:** 2026-09-09 (honesty pass)

Population is measurable globally for free; neighbourhood demographics are not. Splitting the single "vulnerability" row into a measured population row and an unchanged `NOT FITTED` vulnerability row is more honest than one row carrying both — and it removes the circularity where exposure was derived from the hazard's own input.

---

## D16 — FastAPI added, but never something the demo depends on

**Status:** Accepted  ·  **Recorded:** 2026-09-09 (honesty pass)

The offline build remains the NFR-1 guarantee. The API is additive: live refresh, networked browser clients, and later the chatbot. Anything that would make the page *require* it is out of bounds.

---

## D17 — MapLibre GL removed, replaced with a hand-built SVG map

**Status:** Accepted  ·  **Recorded:** 2026-09-09 (honesty pass)

MapLibre loads its parser in a web worker, and Chrome refuses to create a worker for a page opened from a local file — so the map rendered blank from disk, a direct NFR-1 violation. 392 polygons is trivial geometry. Removing it also dropped ~1.5 MB from the bundle, fixed a styling bug, and brought real keyboard access and correct printing. *(Moved here from `IMPLEMENTATION_PLAN.md` §4.1, where an architectural fact was buried in a frontend note.)*

---

## D18 — One product name: HeatLens. The package stays `heatstress`

**Status:** Accepted  ·  **Recorded:** 2026-09-09 (honesty pass)

Six names were in circulation (HeatLens, HEATSHIELD, Hydra, Heatblast, HeatTwin, "Heat Stress Early Warning") — `api/main.py` alone used two. The UI and docs now use one. The package name stays deliberately different and must not be renamed. Committed `.pptx`/`.pdf` files are left alone and renamed when next regenerated.

---

## D19 — The chatbot answers from tools, never from recall — and removes itself when the API is down

**Status:** Accepted 🚧  ·  **Recorded:** 2026-09-09 (chatbot plan)

A model that can state a number it was never given will eventually state a wrong one, and this project's entire claim is that its numbers are checkable. So every figure in an answer must come back from a tool call over the baked payloads; a numeric guard rejects any that did not; a refusal table covers what the data cannot honestly answer; and advisory copy is substituted verbatim, because a reworded public-health instruction is a new instruction nobody approved. Retrieval runs locally on a ~30 MB static embedding model, so no corpus and no question leaves the machine. NFR-1 outranks the feature: when `/api/health` does not answer the panel hides rather than degrading into a chat box that cannot cite anything. Full design in `IMPLEMENTATION_PLAN.md` §5.4.

---

## D20 — Ship the measured pattern on MODIS at 1 km now, rather than wait for Landsat at 30 m

**Status:** Accepted  ·  **Recorded:** 2026-09-11 (satellite + what-if)

Earth Engine needs a one-off browser sign-in and a Cloud project — a step no script can perform. The alternative to a coarse measurement was not a fine measurement, it was **an indefinite continuation of the guess**, and §2.3 shows the guess correlates 0.197 with reality. ORNL DAAC serves MODIS LST as JSON with no registration, no key and no wait, which is the same reasoning as D2 applied to thermal imagery. The cost is stated in the data itself: 295 distinct pixels behind 392 zones, `zones_per_pixel` and `native_resolution_m` carried in every export. `sources/gee.py` and `--source gee` stay tested and one flag away.

---

## D21 — Sample the containing pixel; never interpolate between them

**Status:** Accepted  ·  **Recorded:** 2026-09-11 (satellite + what-if)

At 926 m the pixel is about the size of a 0.69 km² zone, so bilinear smoothing would manufacture sub-pixel detail the instrument never resolved — a plausible-looking invented pattern, which is the exact failure this project exists to avoid. Neighbouring zones therefore share values and the map is honestly blocky. A test pins it.

---

## D22 — Aqua as the source, Terra as the referee

**Status:** Accepted  ·  **Recorded:** 2026-09-11 (satellite + what-if)

Aqua crosses at 13:30, within half an hour of the 14:00 IST focus hour the kill gate is scored on; Terra crosses at 10:30, before the afternoon peak. Using the better-timed instrument for the number and the other for an independent rank check turns a spare data source into a falsification test — they agree at **0.946** over the 15 coarse blocks.

---

## D23 — The what-if box parses; it never generates

**Status:** Accepted  ·  **Recorded:** 2026-09-11 (satellite + what-if)

A free-text surface is the easiest place in this project to destroy its own credibility, because generated prose sitting where a traceable number belongs is indistinguishable from a traceable number. So the box maps English onto the levers the physics already models, looks the answer up in a grid computed during the bake, and refuses everything else. The rules are authored and tested in `whatif.py`, compiled into `insights.json`, and matched by ~150 lines of TypeScript that cannot compute anything. Refusals reuse the `omitted` reasons already on screen rather than new copy, so there is one wording to keep true.

---

## D24 — Pre-baked grid, not an API call — so the simulator survives the wifi being off

**Status:** Accepted  ·  **Recorded:** 2026-09-11 (satellite + what-if)

Rule 4 of Phase 5 forbids new runtime network calls and physics in TypeScript, and NFR-1 requires the page to work from disk. Both point the same way: run all 44 combinations during the bake and ship the answers as data. Verified with the backend killed — the badge reads OFFLINE and the box still answers. The cost is that only grid points can be asked for; off-grid values snap to the nearest row and the UI says so, rather than interpolating (D21).

---
