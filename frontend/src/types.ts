/**
 * Types mirroring the bake output of scripts/06_bake_web.py.
 *
 * These are hand-written against the actual files in web/data/, not guessed.
 * If the bake script changes shape, this file is the first thing to update —
 * everything downstream is typed off it.
 */

export type MetricKey = "air_temp" | "wbgt" | "utci" | "risk";

/** Provenance status vocabulary. A status string starts with one of:
 *  "measured"   — an instrument observed it
 *  "computed"   — deterministic calculation from published equations
 *  "predicted"  — a model forecast of a future value
 *  "published"  — an international standard
 *  "assumed" / "NOT FITTED" / "NOT CALIBRATED" — the honesty guarantees,
 *  which must remain visible in the UI.
 *  Parsed by statusTone() in ui.tsx and tierOf() in TrustCard.tsx. */
export type ProvenanceStatus = string;

export interface ProvenanceEntry {
  layer: string;
  /** Plain-language name for the layer, shown before the technical one. */
  plain?: string;
  source: string;
  resolution: string;
  status: ProvenanceStatus;
}

/** A declared limitation, in both registers. The UI leads with `plain` and
 *  keeps `technical` available for a domain reader. */
export interface Caveat {
  plain: string;
  technical: string;
}

export interface KillGate {
  air_temp_spread_c: number;
  wbgt_spread_c: number;
  utci_spread_c: number;
  wbgt_damping_ratio: number;
  utci_amplification: number;
  verdict: string;
}

export interface Meta {
  city: string;
  /** "live" for the forecast dataset; absent on the historical hindcast. */
  mode?: "live";
  generated_at_ist?: string;
  forecast_age_minutes?: number | null;
  window_ist?: [string, string];
  /** Colour domains derived from this dataset. The hindcast's domains are tuned
   *  to a 45 degC dry event; reusing them on a 33 degC humid week would render
   *  the whole city pale. When present these win over the built-in defaults. */
  domains?: Record<string, [number, number]>;
  centre: { lat: number; lon: number };
  bbox: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  h3_resolution: number;
  n_cells: number;
  focus: { date: string; hour_ist: number };
  event: string;
  kill_gate: KillGate;
  provenance: ProvenanceEntry[];
  caveats: Caveat[];
  is_placeholder_urban: boolean;
  is_placeholder_vulnerability?: boolean;
  exposure_response: {
    metric: string;
    mmt_c: number;
    beta: number;
    beta_ci: [number, number];
    is_calibrated: boolean;
    source: string;
  };
}

export interface HexProperties {
  h3_index: string;
  /** Nearest named place from OpenStreetMap. This is a LABEL, not an
   *  administrative boundary: the zone closest to the point OSM calls
   *  "Maninagar" is not the Maninagar ward. `place_exact` is false when the
   *  nearest name is far enough away that the UI should say "near". */
  place?: string | null;
  place_exact?: boolean;
  d_ta_c: number;
  intensity: number;
  roads: number;
  green: number;
  water: number;
  exposure: number;
  vulnerability: number;
  population?: number;
  elderly_pct?: number;
  slum_roof_pct?: number;
  peak_hour: number;
  wbgt_focus: number;
  utci_focus: number;
  risk_focus: number;
}

export interface HexFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: HexProperties;
}

export interface HexCollection {
  type: "FeatureCollection";
  features: HexFeature[];
}

export interface HourlySeries {
  air_temp: number[];
  wbgt: number[];
  utci: number[];
  heat_index: number[];
  risk: number[];
}

export interface Hourly {
  meta: {
    city: string;
    date: string;
    hours_ist: number[];
    /** Emitted by the bake fix: true clock labels ("14:30"), because ERA5 sits
     *  on the UTC hour and IST is UTC+5:30 — so the data is at :30 past. */
    labels_ist?: string[];
    uhi_amplitude_c: number;
  };
  hexes: Record<string, HourlySeries>;
}

export interface NightRecovery {
  date: string;
  min_c: number;
  max_c: number;
}

export interface City {
  city: string;
  timestamps_ist: string[];
  air_temp: number[];
  wbgt: number[];
  utci: number[];
  heat_index: number[];
  night_recovery: NightRecovery[];
}

export interface PersonaAssessment {
  persona: string;
  label: string;
  wbgt_c: number;
  limit_c: number;
  strain_ratio: number;
  safe_work_min_per_hour: number;
  verdict: string;
  severity: "low" | "moderate" | "high" | "severe" | "critical";
  basis: string;
}

export interface Persona {
  label: string;
  notes: string;
  metabolic: string;
  limit_c: number;
  vulnerability_offset_c: number;
  basis: string;
  safe_minutes_by_hour: number[];
  total_safe_hours: number;
  full_capacity_hours: number[];
  assessment_at_focus: PersonaAssessment;
}

export interface Personas {
  date: string;
  order: string[];
  personas: Record<string, Persona>;
}

export interface Advisory {
  zone_id: string;
  headline: string;
  severity: string;
  colour: string;
  utci_c: number;
  wbgt_c: number;
  safe_work_note: string;
  text: Record<string, string>;
  languages_verified: Record<string, boolean>;
  cap_xml: string;
}

export interface Driver {
  driver: string;
  share: number;
  delta_utci_c: number;
  direction: "raises" | "lowers";
}

export interface Scenario {
  key: string;
  label: string;
  detail: string;
  cost: string;
  basis: string;
  modelled: boolean;
  reduction_pct?: number;
  unsafe_before?: number;
  unsafe_after?: number;
  utci_before?: number;
  utci_after?: number;
  delta_c?: number;
  scope?: string;
  zones_treated?: number;
}

export interface Action {
  title: string;
  detail: string;
  impact: string;
  evidence: string;
}

/** One pre-computed what-if result. Every field was produced by the Python
 *  physics during the bake — nothing here is calculated in the browser. */
export interface CoolingRow {
  shade: number;
  greening: number;
  zones_treated: number;
  utci_before: number;
  utci_after: number;
  delta_c: number;
}

export interface SchedulingRow {
  shift_start: number;
  persona: string;
  window: string;
  unsafe_before: number;
  unsafe_after: number;
  reduction_pct: number;
  covers_full_shift: boolean;
}

export interface ScenarioGrid {
  axes: {
    shade: number[];
    greening: number[];
    shift_start: number[];
    persona: string[];
  };
  cooling: CoolingRow[];
  scheduling: SchedulingRow[];
  basis: string;
}

/** A parser rule authored and tested in `src/heatstress/whatif.py`, compiled
 *  into the payload so the matcher can run offline. */
export interface Intent {
  id: string;
  pattern: string;
  parameter: string;
  transform: "hour" | "percent" | "default" | "literal";
  value?: number | string;
}

export interface RefusalRule {
  id: string;
  pattern: string;
  kind: "not_modelled" | "never_claim";
  omitted_item?: string;
  reason?: string;
}

export interface Insights {
  date: string;
  drivers: Driver[];
  scenarios: Scenario[];
  actions: Action[];
  omitted: { item: string; why: string }[];
  scenario_grid?: ScenarioGrid;
  intents?: Intent[];
  refusals?: RefusalRule[];
}

export interface HeatData {
  meta: Meta;
  hexes: HexCollection;
  hourly: Hourly;
  city: City;
  personas: Personas;
  advisory: Advisory;
  insights: Insights;
}
