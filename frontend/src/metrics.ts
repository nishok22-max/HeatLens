import type { MetricKey } from "./types";

/** Magma-family ramp, light (low) to dark (high). Perceptually uniform and
 *  colourblind-safe; kept in sync with the tokens in index.css. */
export const RAMP = [
  "#fff6e6",
  "#fddfb0",
  "#fbb97e",
  "#f78f65",
  "#e35d63",
  "#c03d73",
  "#8c2a7c",
  "#4d1471",
] as const;

export interface MetricDef {
  key: MetricKey;
  /** Technical name. Kept, never dropped — it is what a domain judge looks for. */
  label: string;
  /** Plain-language name, shown FIRST. Leading with "UTCI" loses the room;
   *  deleting it loses credibility. So we lead with meaning and keep the term. */
  plain: string;
  short: string;
  unit: string;
  /** FIXED domain, deliberately not derived from the visible hour.
   *
   *  An auto-rescaling legend would make the map lie: the coolest cell at 04:00
   *  would render the same colour as the coolest cell at 14:00, hiding the very
   *  diurnal swing the scrubber exists to show. Domains are set from the full
   *  focus-day range of the baked data, rounded outward. */
  domain: [number, number];
  decimals: number;
  description: string;
}

export const METRICS: Record<MetricKey, MetricDef> = {
  air_temp: {
    key: "air_temp",
    label: "Air temperature",
    plain: "Air temperature",
    short: "Air",
    unit: "°C",
    domain: [28, 47],
    decimals: 1,
    description:
      "What a thermometer in the shade reads. This is what heatwave warnings normally use — and on its own it is a poor guide to danger.",
  },
  wbgt: {
    key: "wbgt",
    label: "WBGT",
    plain: "Heat stress for workers",
    short: "WBGT",
    unit: "°C",
    domain: [24, 34],
    decimals: 1,
    description:
      "The world standard for deciding how long people can safely work outdoors. Because it leans heavily on humidity, it under-states danger in dry heat.",
  },
  utci: {
    key: "utci",
    label: "UTCI",
    plain: "What the heat feels like",
    short: "UTCI",
    unit: "°C",
    domain: [25, 63],
    decimals: 1,
    description:
      "Combines heat, humidity, wind and sunshine into what the weather actually feels like to a human body. The best single layer for this event.",
  },
  risk: {
    key: "risk",
    label: "Health risk index",
    plain: "Who is at risk",
    short: "Risk",
    unit: "",
    domain: [0, 0.55],
    decimals: 3,
    description:
      "Combines how dangerous the heat is, how many people are there, and how vulnerable they are. Relative only — not calibrated to local health records.",
  },
};

export const METRIC_ORDER: MetricKey[] = ["air_temp", "wbgt", "utci", "risk"];

/** Colour for a value, used by the legend, the hex map and the cell detail
 *  chips. The SVG map calls this per cell -- see HexMap.tsx for why there is no
 *  MapLibre paint expression doing it instead. */
export function colourFor(value: number, metric: MetricDef): string {
  const [lo, hi] = metric.domain;
  if (!Number.isFinite(value)) return "#cccccc";
  const t = Math.min(1, Math.max(0, (value - lo) / (hi - lo)));
  return RAMP[Math.min(RAMP.length - 1, Math.round(t * (RAMP.length - 1)))];
}

/** Ink colour that stays legible on a given ramp swatch. */
export function inkOn(value: number, metric: MetricDef): string {
  const [lo, hi] = metric.domain;
  const t = Math.min(1, Math.max(0, (value - lo) / (hi - lo)));
  return t > 0.55 ? "#ffffff" : "#1b1a17";
}

export function formatValue(value: number, metric: MetricDef): string {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(metric.decimals)}${metric.unit ? " " + metric.unit : ""}`;
}

/** Scale mode for the map fill.
 *
 *  ABSOLUTE  fixed domain across all 24 hours. Colours are comparable between
 *            hours, so scrubbing shows the real diurnal swing — but at the peak
 *            hour every cell sits at the top of the ramp and intra-city
 *            structure flattens out.
 *  CONTRAST  domain rescaled to the visible hour. Reveals the spatial pattern,
 *            at the cost of comparability between hours.
 *
 *  Both are legitimate; showing one without saying which is not. The legend
 *  states the active mode and the numeric domain, so a reader can never mistake
 *  a rescaled frame for an absolute one.
 */
export type ScaleMode = "levels" | "absolute" | "contrast";

/** Discrete colours for the five plain-language levels (see plain.ts).
 *  A magma-family ordinal ramp, checked with the dataviz validator
 *  (`validate_palette.js --ordinal`, white surface): monotone light->dark,
 *  every step gap >= 0.06 L, single hue family, and the palest step clears
 *  2:1 against the card (2.07:1) -- the earlier #fde7c0 did not (1.21:1).
 *  Every use pairs the colour with the level's name (WCAG 1.4.1). */
export const TONE_COLOUR: Record<
  "low" | "moderate" | "high" | "severe" | "critical",
  { bg: string; ink: string }
> = {
  low: { bg: "#eba660", ink: "#1b1a17" },
  moderate: { bg: "#e2753f", ink: "#1b1a17" },
  high: { bg: "#cf485b", ink: "#ffffff" },
  severe: { bg: "#9b2c78", ink: "#ffffff" },
  critical: { bg: "#4d1471", ink: "#ffffff" },
};

/** Domain for a metric, preferring one supplied by the dataset.
 *  A dataset baked from a 33 degC humid week needs different limits from one
 *  baked from a 45 degC dry event; using the wrong one hides everything. */
export function domainFor(
  metric: MetricKey,
  supplied?: Record<string, [number, number]>,
): [number, number] {
  const d = supplied?.[metric];
  return d && d.length === 2 ? d : METRICS[metric].domain;
}

export function colourInDomain(value: number, domain: [number, number]): string {
  const [lo, hi] = domain;
  if (!Number.isFinite(value) || hi <= lo) return "#cccccc";
  const t = Math.min(1, Math.max(0, (value - lo) / (hi - lo)));
  return RAMP[Math.min(RAMP.length - 1, Math.round(t * (RAMP.length - 1)))];
}

/** Pad a min/max pair outward slightly so the extremes are not pinned to the
 *  very ends of the ramp, which reads as clipping. */
export function paddedDomain(lo: number, hi: number): [number, number] {
  if (!(hi > lo)) return [lo - 0.5, lo + 0.5];
  const pad = (hi - lo) * 0.06;
  return [lo - pad, hi + pad];
}
