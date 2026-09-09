# Product Requirements Document
## Extreme Heatwave Early Warning and Human Thermal Stress Index

**Problem statement:** Smart India Hackathon — *Extreme Heatwave Early Warning and Human Thermal Stress Index*
**Pilot city:** Ahmedabad (23.03 N, 72.58 E) · **Status:** prototype backend complete, 135 tests passing
**Scope tags:** `[P]` = built in the 3-day prototype · `[V1]` = production, after validation

---

## 1. Problem & Opportunity

| | |
|---|---|
| **Problem** | Heat warnings describe the weather, not its effect on people. They are too coarse spatially, too late temporally, and physiologically incomplete. |
| **Why the current signal fails** | IMD declares heatwaves on dry-bulb temperature at district scale, 1–2 days ahead. That number cannot distinguish 40 °C at 20 % humidity (a workable day) from 40 °C at 70 % humidity (potentially lethal), because it ignores how a body actually sheds heat: radiation, convection, and above all evaporation — which humidity switches off. |
| **Consequence** | Heat deaths are systematically undercounted. The large majority of India's workforce is informal and outdoor, so "stay indoors" is not advice available to them. Municipal bodies get 1–2 days when they need 3–5 to mobilise staff, stock ORS, position water tankers, and shift work hours. |
| **Proof intervention works** | Ahmedabad's 2013 Heat Action Plan — India's first, written after the May 2010 heatwave — is credited in published evaluation with averting a substantial number of deaths annually. The bottleneck is not whether warnings help; it is that they are crude and city-wide. |
| **Opportunity** | Shift the unit of forecast from *degrees* to *physiological strain, per neighbourhood, per body* — and wire it directly to municipal action. |

> Verify the 2010 casualty figure and the HAP evaluation against primary sources before quoting them on stage. Judges check numbers like these.

### 1.1 What we learned building it that sharpens the problem

Two findings from the real data changed how this problem should be framed:

**The May 2010 Ahmedabad event was *dry* heat (13–16 % RH), not humid heat.** Humidity was not the killer there. So "humidity kills" is too narrow a thesis. The correct, stronger claim is that **temperature alone misleads in both directions**:

- In humid heat, air temperature *understates* danger.
- In dry heat, WBGT *understates* danger — at the 2010 peak, WBGT read 33.4 °C ("very high") while UTCI read 61.2 °C ("extreme heat stress").

**The killer at Ahmedabad was the nights.** Overnight minima across the event ran 26.8, 27.0, 26.8, 26.7, 28.9, 30.2, 30.7 °C — six consecutive nights with no drop below 27 °C. At midnight on 21 May, UTCI was still 33.1 °C ("strong heat stress"). A daytime-maximum warning is blind to this entirely.

---

## 2. Goals & Non-Goals

**Goals**

1. Compute defensible thermal stress indices (WBGT, UTCI, Heat Index) from temperature **+ humidity + wind + radiation** — never temperature alone.
2. Resolve those indices **below city scale**, making intra-city variation visible.
3. Translate thermal stress into **physiological outcomes per persona** — safe working minutes, strain relative to an occupational limit — not just a colour.
4. Compose hazard, exposure and vulnerability into a health risk index **with honest uncertainty**.
5. Drive **specific, owner-assigned municipal action**, not just a notification.

**Non-Goals**

- Replacing IMD. We consume meteorological data; we do not produce forecasts.
- Clinical diagnosis or individual medical advice.
- Nationwide coverage at launch. One city, deeply, beats twenty shallowly.

---

## 3. Users & Jobs-to-be-Done

| User | Job | Output they need |
|---|---|---|
| **Municipal Commissioner** | Allocate limited resources, 3–5 days out | Ranked neighbourhoods by predicted risk |
| **Municipal Health Officer** | Roster staff, stock ORS, brief UPHCs | Expected excess admissions per facility catchment |
| **Labour / Construction dept** | Decide whether to shift outdoor work hours | Safe working minutes by hour of day |
| **DISCOM planner** | Anticipate cooling load and outage cascades | Zone-level heat-driven demand curve |
| **ASHA / field health worker** | Know which households to visit first | Vulnerable-household list, offline-capable |
| **Outdoor worker / elderly resident** | Know when to stop, hydrate, seek shade | Voice or pictogram alert in local language |

---

## 4. User Stories

- **US-1 `[P]`** As a health officer, I select a date and see the city as a grid coloured by thermal stress, so I can see *which* neighbourhoods are dangerous — not merely that the city is hot.
- **US-2 `[P]`** As a health officer, I click a cell and see *why* it scores as it does — the humidity, radiant load and urban form driving it.
- **US-3 `[P]`** As a labour inspector, I pick a persona and see safe working minutes hour by hour.
- **US-4 `[P]`** As an evaluator, I compare "what a temperature threshold would have shown" against "what this system shows" for the same moment.
- **US-5 `[P]`** As a commissioner, I see the advisory text and machine-readable alert that *would* be dispatched.
- **US-6 `[V1]`** As a commissioner, I receive a 5-day forecast, not a replay of a past event.
- **US-7 `[V1]`** As a commissioner, clicking a red zone produces a printable action order with named owners and quantities.
- **US-8 `[V1]`** As an ASHA worker, I report a heat-illness case by WhatsApp and it recalibrates the model.
- **US-9 `[V1]`** As a planner, I simulate adding tree canopy or cool roofs and watch predicted risk fall.

---

## 5. Functional Requirements

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-1 | Compute WBGT (solar-corrected), UTCI and NOAA Heat Index from T, RH, wind, radiation | P0 `[P]` | ✅ Liljegren WBGT via `thermofeel` |
| FR-2 | Validate every index against published reference values in automated tests | P0 `[P]` | ✅ 175 tests |
| FR-3 | Partition the city into an H3 grid, each cell with a distinct thermal environment | P0 `[P]` | ✅ 392 cells, res 8 |
| FR-4 | Report the intra-city spread statistic (the kill-gate metric) | P0 `[P]` | ✅ `05_kill_gate.py` |
| FR-5 | Per-persona safe working minutes and strain ratio | P1 `[P]` | ✅ ISO 7243 + ACGIH |
| FR-6 | Per-cell vulnerability weight | P1 `[P]` | ⚠️ Declared placeholder |
| FR-7 | Relative risk as Hazard × Exposure × Vulnerability, labelled literature-derived | P1 `[P]` | ✅ uncalibrated by design |
| FR-8 | Interactive map: layer toggle, 24-hour scrubber, cell detail | P0 `[P]` | ✅ React UI, hand-rolled SVG hex map |
| FR-9 | Advisory text in local languages + CAP 1.2 XML payload | P2 `[P]` | ✅ CAP valid; translations unverified |
| FR-10 | Ingest NWP forecasts; probabilistic 5-day output | P0 `[V1]` | ⬜ |
| FR-11 | Fit exposure–response via DLNM on real mortality / ER / ambulance records | P0 `[V1]` | ⬜ blocked on data access |
| FR-12 | Indoor + night-time thermal model by roof typology | P1 `[V1]` | ⬜ |
| FR-13 | Heat Action Plan rules engine producing owner-assigned action orders | P0 `[V1]` | ⬜ |
| FR-14 | Dispatch SMS / WhatsApp / IVR; emit CAP to NDMA SACHET | P1 `[V1]` | ⬜ deliberately not wired |
| FR-15 | Cooling-centre siting optimiser and "what-if" mitigation planner | P2 `[V1]` | ⬜ |

---

## 6. Non-Functional Requirements

| ID | Requirement | Target | Status |
|---|---|---|---|
| NFR-1 | **Demo runs fully offline** — no network dependency on stage | Open from `file://`, wifi off | ✅ 500 KB static assets |
| NFR-2 | **Explainability** — every score decomposes into named drivers | Driver breakdown per cell | ✅ in `hexes.geojson` |
| NFR-3 | **Honest uncertainty** — no accuracy theatre; state approximations | Provenance status per layer | ✅ in `meta.json` |
| NFR-4 | **Data provenance** — source, resolution, and measured/assumed flag | Visible in UI | ✅ 7 layers tagged |
| NFR-5 | **Portability** — free global data only; any city works | Config-driven | ✅ percentile normalisation |
| NFR-6 | Map stays smooth at city scale | ≤ ~3k cells | ✅ 392 cells |

---

## 7. Success Metrics

**Prototype (validation)**

- **M1 — decisive:** intra-city thermal-stress spread ≥ 3 °C. **✅ Met: UTCI spread 3.88 °C**, robust across the whole literature amplitude range (2.57–6.53 °C).
- **M2:** all index implementations pass reference-value tests. **✅ 135 passing.**
- **M3:** hottest/coolest cells physically plausible. **✅ intensity vs roads +0.86, vs water −0.78, vs green −0.29.**
- **M4:** demo completes offline without a crash. ⬜ pending UI.

**Production** — downscaling MAE against held-out stations; lead time achieved; share of high-risk population covered by an intervention within walking distance; ultimately, excess-mortality reduction against matched control wards.

---

## 8. Assumptions, Risks & Open Questions

| | Item | Handling | Outcome |
|---|---|---|---|
| **R1** | Intra-city variation may be too small to matter | The kill gate | ✅ Resolved — PROCEED |
| **R2** | Data access may block (satellite approval, ward shapefiles) | Fallbacks pre-selected | ✅ OSM + H3 sidestepped both |
| **R3** | No local health outcome data | Literature defaults, flagged; calibration seam shipped | ⚠️ Open — needs institutional access |
| **R4** | Would officials act on this? | One phone call | ⬜ Not yet done |
| **A1** | Urban heat structure is stable year-to-year | Justifies decoupling urban form from the weather date | Holds |
| **A2** | Psychrometric ≈ natural wet bulb | **Retired** — Liljegren available | ✅ Eliminated |
| **A3** | UHI amplitude of 3.0 °C | Literature value, **not** locally fitted | ⚠️ Stated; sensitivity swept |

---

## 9. Declared Limitations

These are product properties, not bugs. They must be visible in the UI and stated on stage.

1. **UHI amplitude is assumed.** The spatial *pattern* is measured from real OpenStreetMap urban form; the *magnitude* is a literature value. Present the sensitivity sweep alongside any spread figure.
2. **Vulnerability is a placeholder.** No ward-level demographics were obtainable, so it is a city-wide constant that does not vary between neighbourhoods — meaning risk variation is driven almost entirely by hazard.
3. **Exposure–response is not calibrated** to local health records.
4. **Hindi and Gujarati advisory copy is machine-composed and unverified.** Needs a native speaker before any pitch or dispatch.
5. **Wind, irradiance and pressure are uniform across the city.** Intra-urban variation needs building geometry we do not have.

---

## 10. Out of Scope for the Prototype

Forecasting · trained ML downscaling · DLNM fitting · real alert dispatch · database · authentication · multi-city at launch · action engine · resource optimiser · indoor thermal model.
