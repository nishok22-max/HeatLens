# Product Requirements Document
## HeatLens — Extreme Heatwave Early Warning and Human Thermal Stress Index

**Competition:** Smart India Hackathon — *Extreme Heatwave Early Warning and Human Thermal Stress Index*
**Pilot city:** Ahmedabad (23.03 N, 72.58 E)
**Status:** backend complete · frontend built · live forecast running · **181 tests passing**
**Name:** the product is **HeatLens**. The Python package is called `heatstress`. That difference is on purpose and must not be "tidied up" — renaming the package would break every import and all file history for nothing a user would ever see.

**Tags used in this document**
`[P]` built in the first 3-day prototype · `[L]` built later, during the live/API/frontend work · `[V1]` production work, after validation · `[P5]` Phase 5, the satellite work now in progress

> **How to read this.**
> **Part I** takes the competition problem statement apart clause by clause and says, for each one, what we built and what we did not. Start here.
> **Part II** is our own plan: who it is for, what we require of ourselves, what we measured, and what we know is still weak.
> **Part III** is a plain-English glossary. If a term in Part I or II is unfamiliar, it is defined there.

---

# Part I — The problem statement

## 1. Every requirement, and where we answer it

The problem statement is broken into 13 numbered clauses, **PS-1 to PS-13**, in its own words. The same numbers are used in `ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md`, so you can follow any single requirement across all three documents.

**Key:** ✅ built and working · 🚧 being built now (Phase 5) · ⚠️ answered, but not in the way the clause asks — see §3 · ⬜ not built

| # | What the problem statement asks for | Status | What we actually have |
|---|---|---|---|
| **PS-1** | "Compute a comprehensive **Human Thermal Stress Index** (integrating temperature, humidity, wind, and radiation)" | ✅ | FR-1. All four inputs genuinely change the answer. Wind and sunlight are not decoration — they enter through the Liljegren model, which is the reference method for heat stress in sunlight. Code: `thermal.py`, `psychro.py`, `solar.py` |
| **PS-2** | "Calculate advanced heat stress metrics such as **WBGT, UTCI, or Heat Index** rather than relying on temperature alone" | ✅ | FR-1, FR-2. We compute **all three, not one of three**. Better still, the fact that they disagree with each other turned into a real finding (§4.1). Each one is checked against published reference values in the test suite |
| **PS-3** | "Links it directly to an automated **Mortality Risk Index**" | ⚠️ | FR-7. The whole index is built and runs automatically over every zone and hour. But it is **deliberately not calibrated against real death records**, so it reports *relative* risk — "this zone is worse than that zone" — and never a number of deaths. **This is a deliberate choice, not an unfinished feature. The full reasoning is in §3.1** |
| **PS-4** | "Integrate **historical public health** … data" | ⬜ | FR-11. We have no access to it. Hospital, ambulance and death records in India come from IHIP, 108 EMRI and CRS, and all three need institutional permission we do not have. The plug for it is built and tested (`risk.ExposureResponse.calibrate()`), so when records arrive this is a swap, not a rebuild. §3.1 |
| **PS-5** | "Integrate … **demographic (e.g. elderly or outdoor worker density)**" | ⚠️🚧 | FR-6, FR-18. Phase 5 adds real population counts per zone from a free global dataset (GHS-POP). But that dataset gives **total people only, with no age breakdown** — so it cannot answer "where do the elderly live". That needs a different dataset, scoped as FR-6a. Outdoor workers are modelled as *body types* (FR-5), not yet as a headcount per zone |
| **PS-6** | "Integrate … **localized weather** data" | ✅ | FR-10a. Hourly temperature, humidity, wind, sunlight (three components) and pressure. Refetched automatically whenever the stored copy is more than 15 minutes old |
| **PS-7** | "Predict heat-induced mortality and hospitalization spikes **3 to 5 days in advance**" | ⚠️ | Three separate things here. **Lead time: ✅ done — we forecast 6 days ahead**, which covers the 3–5 day requirement with a day to spare. **Heat-stress and physical-strain spikes: ✅** predicted for every zone, every hour. **Death and hospital-admission counts: ⬜** not produced, for the reason in §3.1 |
| **PS-8** | "**High-resolution** forecasts … hyper-local (**Zone/Ward level**)" | ✅ | FR-3, FR-20. **392 zones, each 0.693 km²** — roughly a 700 m patch. Every zone is labelled with the nearest place name *and the distance to it*, so the screen can say "near Maninagar" without pretending to be an official ward map. Real ward boundaries are `[V1]`, and adding them is a data join, not a rebuild |
| **PS-9** | "A **dynamic GIS-mapped dashboard** providing **color-coded**, hyper-local alerts" | ✅ | FR-8. Built and working: a colour-coded zone map, four switchable layers, a 24-hour time slider, click-through detail per zone, usable by keyboard, and it runs with no internet connection at all |
| **PS-10** | "Paired with **actionable, automated public health advisories**" | ✅ | FR-9, FR-13a. Warning text graded by severity in English, Hindi and Gujarati (the translations are flagged as unchecked), plus instructions written for each official's role and a computed list of recommended actions |
| **PS-11** | "An **API** capable of **pushing automated SMS/WhatsApp** regional alerts" | ⚠️ | FR-19 ✅ + FR-14. **The API is built** — 26 routes. **The alert message itself is built** — valid CAP 1.2 XML, the format India's national alert system accepts. **Only the final "send" step is deliberately switched off**, and §3.2 explains why. This is one connector away from working, not a missing subsystem |
| **PS-12** | "Localized **triggers for city administration to initiate heat action plans** (opening cooling centers, adjusting power grids, shifting outdoor work hours)" | ⚠️ | Three requests, three different answers. **Shifting work hours: ✅ done** — safe working minutes hour by hour, plus a simulator that re-runs the physics on a shifted schedule. **Cooling centres: 🚧** FR-15, Phase 5F. **Power grid: ⬜** FR-21 — we list the electricity planner as a user but built nothing for them yet. The general rules engine is FR-13b `[V1]` |
| **PS-13** | "Help **municipal corporations, healthcare systems, and disaster management authorities** deploy targeted, preemptive interventions" | ✅ | §6, §7. The dashboard has separate views for the commissioner, the health officer, the labour inspector and the field worker |

### 1.1 The score, and what is actually left

**7 of 13 fully built · 5 partly built · 1 not started.**

The five partials are not equally incomplete. Three of them — the forecast lead time, the API, and the work-hour trigger — **are genuinely built**; earlier drafts of this document simply undersold them. What is really still open comes down to three things:

1. **Death and hospital-admission counts** (PS-3, PS-4, PS-7). This is a permissions problem, not a coding problem. §3.1.
2. **Age-specific population data** (PS-5). A dataset swap, scoped as FR-6a.
3. **Electricity-grid triggers** (PS-12). Genuinely not started, scoped as FR-21.

## 2. Things we built that nobody asked for

These are where the project is strongest. None of it is padding — each one exists because the data forced it.

- **A test that could have killed the project.** Before building any screens, we committed to a threshold: if the hottest and coolest parts of the city differed by less than 3 °C of heat stress, then "hyperlocal" was a false premise and we would change direction. The measured answer was **3.88 °C**, so we continued. A test that could have failed is worth far more than one that could only ever confirm what we wanted.
- **Every headline number computed twice, independently.** Once by our own code written from the published equations, once by `thermofeel`, the European weather centre's operational library. The test suite compares them. On mean radiant temperature they agree to **0.005 °C**. When a judge asks "how do you know your numbers are right?", two independent implementations agreeing is a much better answer than a percentage.
- **A finding that contradicts the problem statement's own example.** The problem statement opens with humid heat being more dangerous than dry heat at the same temperature. That is true. But the May 2010 Ahmedabad disaster that led to India's first Heat Action Plan was **dry** heat at 13–16 % humidity — and in those conditions WBGT *understates* the danger while UTCI catches it. So temperature alone misleads in *both* directions, and so does any single index used alone (§4.1).
- **Honesty stored as data, not as a footnote.** Every data layer carries its own source, resolution and a flag saying whether it is measured or assumed, and that travels into the screen. Tests enforce it. This is the machinery that lets us state PS-3's limits clearly instead of hoping nobody asks.
- **It works with no internet.** The entire dashboard opens from a USB stick with wifi switched off. Live demos die on conference networks.

## 3. Two requirements we answer differently than asked

Both of these would have been easy to fake. Saying so plainly is the point.

### 3.1 The "automated Mortality Risk Index" (PS-3, PS-4, PS-7)

**What we built.** The complete index. A dose-response relationship linking heat stress to relative risk, a lag kernel (heat kills over the following days, not only on the day), hazard scaling, and the standard IPCC combination `Risk = ∛(Hazard × Exposure × Vulnerability)`. It runs automatically over every zone and hour, and it drives the map.

**What we will not do.** Print a number of deaths.

**Why.** A mortality index only deserves that name if it has been fitted against real mortality. We have no local health records. Any absolute figure we printed would be a coefficient from a published paper multiplied by a population and then presented as a prediction. It would look more finished and be worth less than nothing: an official who acts on a made-up casualty count and discovers it was wrong never trusts the system again.

**So the index reports relative risk**, labelled `NOT CALIBRATED` in both the data and the screen, with `is_calibrated=False` protected by two tests so it cannot quietly flip to `True` later. The connection point for real data is built, tested and documented — `calibrate()` returns a calibrated copy — so the day records arrive this is one function call. Requests for that data should go out now regardless of build order; even a rejection letter is proof you pursued the real path instead of inventing numbers.

**What we can say instead, which is not nothing:** *which* zones are dangerous, *how much worse* than the city average, *for which kinds of people*, *at which hours of the day*, and (after Phase 5E) *how many residents live in zones that cross a named occupational safety threshold*. That is enough to roster staff, move water tankers and change shift timings.

> **This is a judgement call, and it can be reversed.** If you would rather show a calibrated-looking mortality figure built from published coefficients with a visible caveat, say so and this section gets rewritten. But the two tests asserting `is_calibrated=False` are load-bearing and should be changed knowingly, not by accident.

### 3.2 The "API capable of pushing SMS/WhatsApp alerts" (PS-11)

**Built:** the API (FR-19, 26 routes) and the alert message itself (FR-9 — CAP 1.2 XML, the format India's NDMA SACHET system consumes).

**Deliberately switched off:** the send. Every alert is marked `status=Exercise`, never `Actual`, so no real alerting system would act on it, and no sending credentials exist anywhere in the project.

**Why.** An alerting system that can fire during a demo is a hazard, and a prototype must never emit something real emergency infrastructure would treat as genuine. What is missing is one connector — a Twilio or Gupshup client behind an interface that already exists — and that is a decision for whichever municipal body owns the alert channel, not ours to make for them.

---

# Part II — Our own plan

## 4. The problem, and why existing warnings fail

| | |
|---|---|
| **The problem** | Heat warnings describe the weather, not what it does to people. They cover too large an area, arrive too late, and ignore how a body actually works. |
| **Why today's warnings fail** | India's weather service declares heatwaves using plain air temperature, for a whole district, 1–2 days ahead. That number cannot tell 40 °C at 20 % humidity (a hard but workable day) from 40 °C at 70 % humidity (potentially lethal) — because it ignores how a body sheds heat. A body cools mainly by sweating, and high humidity switches that off. |
| **What follows from that** | Heat deaths get undercounted. Most of India's workforce is informal and works outdoors, so "stay indoors" is not advice available to them. And city governments get 1–2 days when they need 3–5 to move staff, stock rehydration salts, position water tankers and change shift timings. |
| **Evidence that acting works** | Ahmedabad's 2013 Heat Action Plan — India's first, written after the May 2010 disaster — is credited in published evaluations with saving a substantial number of lives every year. So the question is not whether warnings help. It is that they are too crude and cover the whole city at once. |
| **The opportunity** | Change the unit of the forecast from *degrees* to *strain on a specific body, in a specific neighbourhood* — and connect it directly to a decision an official can sign. |

> Check the 2010 death toll and the Heat Action Plan evaluation against original sources before quoting either on stage. Judges verify numbers like these.

### 4.1 Two findings from the real data that sharpened the problem

**The May 2010 Ahmedabad disaster was *dry* heat, at 13–16 % humidity.** Humidity was not the killer there. So "humidity is what kills" is too narrow a thesis. The stronger and more accurate claim is that **temperature alone misleads in both directions**:

- In humid heat, air temperature makes things look *safer* than they are.
- In dry heat, WBGT makes things look *safer* than they are. At the 2010 peak, WBGT read 33.4 °C ("very high") while UTCI read 61.2 °C ("extreme heat stress").

The practical consequence: you cannot pick one index and use it everywhere. Which one to show depends on the city and the event.

**The nights were the real killer.** Overnight lows across the event ran 26.8, 27.0, 26.8, 26.7, 28.9, 30.2 and 30.7 °C — six nights in a row with no drop below 27 °C. At midnight on 21 May, UTCI was still 33.1 °C, which is "strong heat stress". A body needs cool nights to recover; these never came. A warning system built around daytime maximum temperature cannot see this at all.

### 4.2 A third finding, from checking our own data — this one sets the Phase 5 agenda

**Our map of which zones are hotter is thinner than its formula suggests.**

The formula combines four things: `0.55 × buildings + 0.25 × roads − 0.30 × greenery − 0.20 × water`. But building data was switched off (it is the slowest thing to download and was judged not worth the time), so **the buildings number is 0.0 in all 392 zones**. The biggest weight in the project's core formula contributes nothing. Greenery is non-zero in only 175 of 392 zones, averaging 0.023.

What is left is, measurably, **road density**:

```
correlation with road density  = +0.855
correlation with water         = -0.778
correlation with greenery      = -0.286
```

This is a genuine defect, found by inspection, and it is written down here rather than quietly patched by adjusting the weights. It is also the single strongest argument for **FR-16 (satellite temperature)**: replacing a hand-weighted guess about which zones are hotter with an actual measurement.

---

## 5. Goals and non-goals

**Goals**

1. Compute defensible heat-stress numbers (WBGT, UTCI, Heat Index) from temperature **plus humidity, wind and sunlight** — never temperature alone. *(PS-1, PS-2)*
2. Resolve those numbers **below city scale**, so differences within the city become visible. *(PS-8)*
3. Turn heat stress into **physical consequences for a specific person** — how many minutes they can safely work, how close they are to an occupational limit — not just a colour. *(PS-7, PS-12)*
4. Combine hazard, exposure and vulnerability into a health-risk score **that is honest about its uncertainty**. *(PS-3)*
5. Drive **a specific action with a named owner**, not just a notification. *(PS-10, PS-12, PS-13)*
6. **Shrink what is assumed.** Anything that can honestly be measured or fitted should be, and whatever is still assumed must be nameable in one sentence.

**Non-goals**

- Replacing the national weather service. We consume weather data; we do not produce forecasts.
- Medical diagnosis or advice for an individual.
- National coverage at launch. One city, done properly, beats twenty done shallowly.
- Fitting against health outcomes. We have no mortality records, so the risk model stays uncalibrated and **no statistical mortality model is attempted**. Risk is relative only. *(§3.1.)*

---

## 6. Who it is for

| User | What they need to decide | What they need from us | Status |
|---|---|---|---|
| **Municipal Commissioner** | Where to send limited resources, 3–5 days out | Neighbourhoods ranked by predicted risk | ✅ |
| **Municipal Health Officer** | Staff rosters, rehydration stock, clinic briefings | Expected extra admissions per clinic catchment | ⚠️ relative risk per zone; actual admission counts need FR-11 |
| **Labour / Construction dept** | Whether to move outdoor work hours | Safe working minutes, hour by hour | ✅ |
| **Electricity (DISCOM) planner** | Cooling demand and cascading outage risk | A zone-level heat-driven demand curve | ⬜ FR-21 |
| **ASHA / field health worker** | Which households to visit first | A vulnerable-household list, usable offline | ⚠️ zone-level, not per household; offline ✅ |
| **Outdoor worker / elderly resident** | When to stop, drink, find shade | A voice or picture alert in their language | ⚠️ text warnings ✅; voice ⬜ FR-14 |

---

## 7. User stories

- **US-1 `[P]`** As a health officer, I pick a date and see the city as a coloured grid, so I can see *which* neighbourhoods are dangerous — not just that the city is hot.
- **US-2 `[P]`** As a health officer, I click a zone and see *why* it scores as it does — the humidity, the sunlight, the built-up surroundings.
- **US-3 `[P]`** As a labour inspector, I pick a type of worker and see safe working minutes for each hour.
- **US-4 `[P]`** As an evaluator, I compare what a plain temperature threshold would have shown against what this system shows, for the same moment.
- **US-5 `[P]`** As a commissioner, I see the warning text and the machine-readable alert that *would* be sent.
- **US-6 `[L]`** As a commissioner, I see a live forecast six days out, not just a replay of a past event. *(One forecast, not a range of possibilities — that is FR-10b.)*
- **US-7 `[V1]`** As a commissioner, clicking a red zone gives me a printable order with named owners and quantities.
- **US-8 `[V1]`** As an ASHA worker, I report a heat illness by WhatsApp and the model learns from it.
- **US-9 `[P5]`** As a planner, I simulate planting trees or painting roofs white and watch predicted risk fall — with the result recalculated from a fitted model, not nudged by hand.
- **US-10 `[P5]`** As a commissioner, I ask where cooling centres should go and get a curve showing how much more population each additional centre covers — not a list ranked by the hazard itself.
- **US-11 `[V1]`** As an electricity planner, I see a zone-level demand curve for the days ahead, so I can pre-position load and anticipate cascading outages.

---

## 8. Functional requirements

The **PS** column links each requirement back to the problem-statement clause in §1 that it answers.

| ID | PS | Requirement | Priority | Status |
|---|---|---|---|---|
| FR-1 | PS-1, PS-2 | Compute WBGT (corrected for sunlight), UTCI and the NOAA Heat Index from temperature, humidity, wind and radiation | P0 `[P]` | ✅ Liljegren WBGT via `thermofeel` |
| FR-2 | PS-2 | Check every index against published reference values in automated tests | P0 `[P]` | ✅ **181 tests** |
| FR-3 | PS-8 | Divide the city into a grid where each cell has its own thermal environment | P0 `[P]` | ✅ 392 cells, 0.693 km² each, ~272 km² total |
| FR-4 | — | Report the spread between hottest and coolest zone (the go/no-go measurement) | P0 `[P]` | ✅ `05_kill_gate.py` |
| FR-5 | PS-7, PS-12 | Safe working minutes and strain level per person type, hour by hour | P1 `[P]` | ✅ ISO 7243 + ACGIH; six person types including `elderly` and outdoor construction |
| FR-6 | PS-5 | Exposure and vulnerability weight per zone | P1 `[P]` | ⚠️ both are placeholders today; **FR-18** makes exposure real and leaves vulnerability a city-wide constant |
| **FR-6a** | PS-5 | **Population by age — where the elderly live.** GHS-POP gives total people with no age split, so PS-5's "elderly density" needs WorldPop age-sex data or Census 2011 ward age tables joined onto the grid | P1 `[V1]` | ⬜ **newly scoped** — the honest gap behind PS-5 |
| FR-7 | PS-3 | Relative risk as Hazard × Exposure × Vulnerability, labelled as literature-derived | P1 `[P]` | ✅ built and running, **uncalibrated on purpose — §3.1** |
| FR-8 | PS-9 | Interactive map: layer switch, 24-hour slider, zone detail | P0 `[P]` | ✅ **built** — hand-built SVG map, 4 layers, keyboard-usable |
| FR-9 | PS-10, PS-11 | Warning text in local languages plus a CAP 1.2 XML alert payload | P2 `[P]` | ✅ CAP is valid and marked `Exercise`; translations unchecked |
| FR-10a | PS-6, PS-7 | Pull a live forecast and republish on a schedule — **one forecast, 6 days ahead** | P0 `[L]` | ✅ **covers the 3–5 day requirement with a day spare**; Open-Meteo via `live.py`, FastAPI, and a GitHub job every 6 hours |
| FR-10b | PS-7 | **Range of possible outcomes** instead of one — ensemble spread, probability of crossing a threshold | P0 `[V1]` | ⬜ |
| FR-11 | PS-3, PS-4, PS-7 | Fit the dose-response against real death / emergency / ambulance records, enabling **absolute death and admission projections** | P0 `[V1]` | ⬜ blocked on data access — **deliberately not attempted; §3.1**. The `calibrate()` connection point is built and tested |
| FR-12 | — | Indoor and night-time temperature model by roof type | P1 `[V1]` | ⬜ — the highest-value item left (see the night finding in §4.1) |
| FR-13a | PS-10, PS-12 | Computed recommended actions and role-specific instructions, plus an explicit list of what we deliberately do *not* offer | P1 `[P]` | ✅ `insight.py` |
| FR-13b | PS-12 | Full Heat Action Plan rules engine producing orders with named owners | P0 `[V1]` | ⬜ |
| FR-14 | PS-11 | Sending connector: SMS / WhatsApp / voice; deliver CAP to NDMA SACHET | P1 `[V1]` | ⬜ **deliberately not wired — §3.2.** The message and the API exist; only the send is off |
| FR-15 | PS-12 | Cooling-centre placement and a what-if planner for mitigation | P2 `[P5]` | 🚧 planned — unblocked by FR-18. Greedy best-coverage over population, and **the curve of diminishing returns is the deliverable**, not the list of sites |
| FR-16 | PS-8 | **Satellite land-surface temperature per zone.** Landsat 8/9 thermal band, April–May 2023–2025, under 10 % cloud, quality-masked, averaged per zone on Google's servers. MODIS Aqua used as an independent coarse sanity check — **not** mixed in | P0 `[P5]` | 🚧 planned |
| FR-17 | PS-8 | **A fitted model from city shape to satellite temperature, with honest error bars.** Ridge regression on 6 inputs, tested by holding out whole geographic blocks, with 90 % prediction intervals. The operational number still comes from the **observed** satellite measurement; the model fills cloud gaps, supplies the error bar, and powers the what-if simulator | P0 `[P5]` | 🚧 planned |
| FR-18 | PS-5 | **Real population per zone.** JRC GHS-POP 2020 summed per zone; exposure scaled by percentile, raw headcount kept. Removes the circularity where exposure was derived from the hazard's own input | P1 `[P5]` | 🚧 planned |
| **FR-19** | PS-11 | **Public read API.** FastAPI service exposing the whole payload — 26 routes across `/api/v1/historical/*`, `/api/v1/forecast/*` and `/api/v1/live/*` (map, summary, hourly, per-zone, person types, advisory, insights, metadata), plus health. Read-only on purpose; the offline build stays the demo path | P1 `[L]` | ✅ **built** |
| **FR-20** | PS-8 | **Human-readable zone names.** Every zone carries its nearest place name *and the distance to it*, so the screen says "near Maninagar" and nobody mistakes a nearest-place label for an official ward | P2 `[P]` | ✅ **built** — `03_place_names.py` |
| **FR-21** | PS-12 | **Zone-level heat-driven electricity demand signal** for grid planning, plus the cascading-outage risk that follows | P2 `[V1]` | ⬜ **newly scoped** — named in PS-12 and in §6, genuinely not started |
| FR-22 | PS-8 | Roll zones up to official ward boundaries when a boundary file is available | P2 `[V1]` | ⬜ the grouping code is already boundary-agnostic, so this is a join |

---

## 9. Non-functional requirements

| ID | Requirement | Target | Status |
|---|---|---|---|
| NFR-1 | **The demo runs fully offline** — nothing on stage depends on a network | Opens from a local file with wifi off | ✅ ~520 KB of data, built into a single 1.7 MB page |
| NFR-2 | **Explainable** — every score breaks down into named causes | Cause breakdown per zone | ✅ in `hexes.geojson` |
| NFR-3 | **Honest about uncertainty** — no fake precision; approximations stated | A status per data layer | ✅ in `meta.json` |
| NFR-4 | **Traceable data** — source, resolution, and a measured/assumed flag | Visible on screen | ✅ 7 layers tagged (8 after FR-18) |
| NFR-5 | **Portable** — free global data only, so any city works | Driven by a config file | ✅ percentile scaling; Landsat and GHS-POP are global, so FR-16/18 keep this true |
| NFR-6 | The map stays responsive at city scale | Up to ~3,000 zones | ✅ 392 zones |
| NFR-7 | **A fixed vocabulary for data status.** Every status is one of `measured` · `published standards` · `fitted (cross-validated)` · `ASSUMED -- not fitted locally` · `NOT FITTED` · `NOT CALIBRATED`, enforced by a test — plus a per-row `assumes:` list wherever a measured layer still rests on an assumption | No free-text statuses | 🚧 planned with `[P5]` — a half-measured system is exactly where a screen drifts away from the truth |

---

## 10. How we measure success

**Prototype validation**

- **M1 — the decisive one:** heat-stress spread across the city of at least 3 °C. **✅ Met: UTCI spread is 3.88 °C**, and it stays above the line across the entire plausible range from the literature (2.57–6.53 °C). The margin over the threshold is **0.88 °C**, and a test now guards it so the verdict cannot flip silently when the offset changes.
- **M2:** every index passes its reference-value tests. **✅ 181 passing.**
- **M3:** the hottest and coolest zones are physically plausible. **✅ correlation with roads +0.855, with water −0.778, with greenery −0.286** — plausible, but see §4.2: with buildings at zero this is very nearly a road map, which is exactly what FR-16 replaces.
- **M4:** the demo completes offline without crashing. ⬜ **The frontend is built, but the wifi-off test has still not been ticked off** and must happen before any pitch.
- **M5 `[P5]` — the model's own go/no-go, written down *before* fitting:** the fitted model ships only if it scores at least **0.25** when tested on held-out geographic blocks (`min_spatial_cv_r2` in the config file), and its 90 % error bars actually contain the true value about 90 % of the time, within 5 points. If it misses, the wiring step refuses to run and the existing method stays. Same discipline as M1: a threshold set in advance and honoured either way.

**Production** — prediction error against weather stations held back from fitting; lead time actually achieved; share of at-risk population within walking distance of an intervention; and ultimately, reduction in excess deaths compared with similar wards that did not get the system.

---

## 11. Assumptions, risks and open questions

| | Item | How we handle it | Where it stands |
|---|---|---|---|
| **R1** | Variation within the city might be too small to matter | The pre-committed 3 °C threshold | ✅ Resolved — 3.88 °C, margin 0.88 °C |
| **R2** | Data access might block us (satellite approval, ward boundary files) | Fallbacks chosen in advance | ✅ OpenStreetMap and a hex grid avoided both. Satellite access has since been granted, so FR-16 is unblocked |
| **R3** | No local health outcome data | Published defaults, clearly flagged; the connection point built | ⚠️ Open — needs institutional access. **This is the one thing standing between PS-3/PS-4/PS-7 and full coverage** |
| **R4** | Would officials actually act on this? | One phone call | ⬜ Not yet made |
| **R5 `[P5]`** | **The satellite passes over Ahmedabad at about 10:45 in the morning; our focus hour is 2 pm** | The satellite gives us the *pattern* of which zones are hotter, not the 2 pm temperature. MODIS Aqua passes at about 1:30 pm and is the check that the pattern holds at a near-peak time. The claim is "the coarse pattern repeats at a near-peak overpass", never "this is a 2 pm measurement" | ⬜ To be carried as an `assumes:` entry in the data |
| **R6 `[P5]`** | **GHS-POP counts where people *live*, and it is modelled rather than observed** | At 2 pm people are at work, so a residential count is the wrong denominator for a daytime statistic — and it cannot answer "elderly density" at all (FR-6a). Exactly one narrowly-defined, checkable statistic is allowed; "N people at risk" stays refused | ⬜ To be carried as a caveat field in the returned data |
| **R7 `[P5]`** | **The fitted model might fail its own threshold (M5)** | Threshold set before fitting and honoured; if it fails, the existing method stays and we publish the number anyway | ⬜ Being able to fail is the point |
| **R8 `[P5]`** | **Zones containing the river could dominate any fit** | Report the fit with and without them, so nobody can say the result rests on the Sabarmati | ⬜ |
| **A1** | The pattern of which areas are hotter is stable year to year | Lets us separate city shape from the weather date | Holds |
| **A2** | A simpler wet-bulb approximation is close enough | **Retired** — the full Liljegren model is available | ✅ Eliminated |
| **A3** | The city is 3.0 °C hotter in its hottest parts | A literature value, **not** measured here | ⚠️ Still live today; **to be replaced by A4** once FR-16/17 land |
| **A4 `[P5]`** | **`alpha = 0.40` — how much surface heat translates into air heat** | Much narrower than A3: the pattern becomes measured and only this one number stays assumed. It cannot be fitted without air-temperature stations we do not have. Tested across the range 0.30–0.50, exactly as the 3.0 °C figure is today | ⬜ Replaces A3 — superseded, not deleted |

---

## 12. Known limitations

These are properties of the product, not bugs. They must be visible on screen and stated on stage.

1. **How much hotter is assumed.** *Which* zones are hotter is measured from real map data; *how much* hotter is a published average. Always show the sensitivity range alongside any spread figure. *(After FR-16/17 this narrows to: the pattern is measured from satellite temperature, and one number — `alpha` — stays assumed.)*
2. **The city-shape score is effectively a road map.** Buildings are zero in every zone, so the 0.55 weight on them contributes nothing (§4.2). Stated plainly rather than fixed by re-weighting.
3. **Vulnerability is a placeholder, and population has no age breakdown.** We could not obtain neighbourhood demographics, so vulnerability is one city-wide number and risk variation comes almost entirely from hazard. FR-18 makes the exposure half real; vulnerability stays constant, and elderly density (FR-6a) is not available at all yet.
4. **The dose-response is not fitted to local health records**, so **no death or admission count is produced** (§3.1).
5. **Alert sending is switched off** — the message is valid and the API serves it, but nothing is sent (§3.2).
6. **The Hindi and Gujarati warning text is machine-composed and unchecked.** It needs a native speaker before any pitch or real use.
7. **Wind, sunlight and pressure are treated as uniform across the city.** Varying them within the city needs building geometry we do not have.
8. **Zone names are nearest-place labels, not administrative areas.** "Maninagar" means the zone closest to the point OpenStreetMap calls Maninagar, with the distance stored alongside. It is not the Maninagar ward.
9. **`[P5]` The 90 % error bar will cover satellite-prediction error only** — not `alpha`, not the physics, not the weather forecast. That sentence ships as a field in the data, not only in a code comment.

### 12.1 What may and may not be claimed on stage

**Safe to claim today:** all three heat indices, each checked against published references and independently cross-checked by a second implementation · variation within the city is real, and was tested against a threshold that could have failed · a 6-day forecast horizon · safe working minutes per person type from published occupational standards · a working API and a valid CAP 1.2 alert payload · a dashboard that runs with no internet.

**Safe to claim after `[P5]`:** which zones are hotter is *measured* from satellite · the relationship between city shape and that pattern is *fitted* and reported on held-out geography · every offset carries a 90 % error bar whose real-world coverage was checked · exposure uses real residential population, so risk is no longer circular with hazard · exactly one number stays assumed, and we can name it.

**Never claim:** a death or hospital-admission count · "N people at risk" · "it predicts air temperature" (it predicts a *surface* pattern; `alpha` makes the conversion) · "validated" — say **"cross-checked against held-out satellite measurements"**, because there is no air-temperature station network here · "the urban heat island in Ahmedabad is X °C" · the in-sample fit quality as a headline number · any single model coefficient read as a cause (greenery and satellite greenness measure the same thing, which is fine for prediction and fatal for explanation) · the satellite composite as a 2 pm measurement · "we use a LightGBM model" · that alerts are being sent.

---

## 13. Out of scope for the prototype

Statistical mortality modelling · probability ranges instead of a single forecast · real alert sending · a database · user accounts · multiple cities at launch · the full rules engine · the indoor temperature model · gradient-boosted or random-forest models (see M5 and the sample-size argument in `ARCHITECTURE.md` §6 D12) · optimisation solvers for siting · road-network travel times · error bars that vary from zone to zone.

*Moved out of this list into `[P5]`:* the fitted model (FR-17) and the siting planner (FR-15).
*Newly scoped instead of silently dropped:* elderly density (FR-6a), grid load (FR-21), ward roll-up (FR-22).

---

# Part III — Glossary

Plain-English definitions for every technical term used above.

| Term | What it means |
|---|---|
| **WBGT** | Wet Bulb Globe Temperature. The occupational heat-stress standard. It blends a wet thermometer reading (70 %), a black-globe reading that captures sunlight (20 %) and plain air temperature (10 %). Labour rules are written against it. |
| **UTCI** | Universal Thermal Climate Index. "What the weather feels like to a standard person", combining temperature, humidity, wind and radiant heat into one equivalent temperature. |
| **Heat Index** | The US weather service's "feels like" number, from temperature and humidity only. |
| **Liljegren model** | The reference method for computing WBGT outdoors in sunlight from ordinary weather data. It needs wind and radiation, which is why both matter to us. |
| **Wet bulb** | What a thermometer reads with a wet cloth around it. In dry air, evaporation cools it well below air temperature. In humid air it barely drops — which is exactly why humidity is dangerous. |
| **Vapour pressure** | The actual amount of water in the air, expressed as a pressure. Unlike relative humidity, it does not change when the air warms — which is why we carry it between zones (see `ARCHITECTURE.md` §2.1). |
| **H3** | Uber's system for dividing the world into equal-sized hexagons. We use level 8, where each hexagon is 0.693 km². Equal areas mean per-zone numbers are directly comparable, which is not true of real wards. |
| **LST** | Land Surface Temperature. How hot the *ground and roofs* are, measured by satellite. Always hotter and more variable than the air above it — the two must never be confused. |
| **Landsat ST_B10** | The thermal band of the Landsat 8/9 satellites, which is what gives us surface temperature at 30 m resolution. |
| **NDVI / NDBI** | Satellite indices for how green (NDVI) and how built-up (NDBI) a place is. |
| **MODIS Aqua** | A satellite that passes over at about 1:30 pm — close to our 2 pm focus hour, but far too coarse (1 km) to see a single zone. We use it only to check the broad pattern. |
| **GHS-POP** | A free global dataset estimating how many people live in each 100 m square. Modelled rather than counted, and residential only. |
| **Ridge regression** | A straight-line fit that deliberately keeps its coefficients small, so it stays stable when inputs overlap. Chosen because we effectively have about 20 independent locations, not 392. |
| **Spatial block cross-validation** | Testing a model by hiding whole *geographic areas*, not scattered individual zones. Hiding one hexagon leaves most of its neighbours in the training data, which flatters the score. Hiding a whole block does not. |
| **Conformal interval** | A way to attach an error bar with a guarantee: a 90 % interval really does contain the truth about 90 % of the time, checked by holding data back rather than assumed from a formula. |
| **alpha (`alpha`)** | How much of a surface-temperature difference shows up as an air-temperature difference. We use 0.40. It cannot be fitted without ground weather stations, so it stays the one assumed number. |
| **Dose-response / exposure-response** | The curve connecting how hot it is to how much health harm follows. Ours comes from published studies, not local data — which is why risk is relative only. |
| **Lag kernel** | Heat does not kill only on the hottest day; deaths continue for several days afterwards. The lag kernel spreads the effect across those following days. |
| **CAP 1.2** | Common Alerting Protocol — the international XML format for emergency alerts, accepted by India's NDMA SACHET system. Ours is always marked `Exercise`, never `Actual`. |
| **ISO 7243 / ACGIH** | The published occupational standards giving safe heat limits and work/rest splits according to how hard someone is working. |
| **Kill gate** | Our own go/no-go test, with the threshold written down before measuring. Used twice: once for city-wide variation (M1) and once for the fitted model (M5). |
| **Percentile scaling** | Scaling a number by where it ranks rather than against a fixed cap. Keeps the system portable: a cap tuned on Ahmedabad would misscale Chennai. |
| **Provenance** | The record, carried in the data itself, of where each layer came from and whether it is measured or assumed. |
