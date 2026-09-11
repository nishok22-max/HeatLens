/**
 * Plain-language layer.
 *
 * The technical layer (metrics.ts, the Python core) is correct but unreadable to
 * anyone who does not already know what a wet-bulb globe temperature is. This
 * module supplies the human-readable half of every number so the UI can lead
 * with meaning and keep the jargon as supporting detail — rather than the other
 * way round.
 *
 * RULE OBSERVED THROUGHOUT: never replace a technical term, always precede it.
 * "What the heat feels like (UTCI)" keeps the domain judge and admits the rest
 * of the room. Deleting "UTCI" would lose credibility; leading with it loses
 * the audience.
 */

export interface Verdict {
  /** Two or three words a non-expert understands immediately. */
  label: string;
  /** One sentence saying what it means for a person. */
  detail: string;
  /** Severity, for colour and ordering. Never the only signal (WCAG 1.4.1). */
  tone: "low" | "moderate" | "high" | "severe" | "critical";
}

/** UTCI, mapped from the official thermal-stress bands. */
export function utciVerdict(value: number): Verdict {
  if (!Number.isFinite(value))
    return { label: "No reading", detail: "Outside the model's valid range.", tone: "low" };
  if (value >= 46)
    return {
      label: "Extreme",
      detail: "Dangerous within minutes. Heat stroke is a real risk even for healthy adults.",
      tone: "critical",
    };
  if (value >= 38)
    return {
      label: "Very severe",
      detail: "Dangerous after sustained exposure. Outdoor work should stop.",
      tone: "severe",
    };
  if (value >= 32)
    return {
      label: "Severe",
      detail: "Frequent rest and shade needed. Vulnerable people should stay indoors.",
      tone: "high",
    };
  if (value >= 26)
    return {
      label: "Noticeable",
      detail: "Uncomfortable but manageable. Keep drinking water.",
      tone: "moderate",
    };
  return { label: "Comfortable", detail: "No meaningful heat stress.", tone: "low" };
}

/** WBGT, against the occupational bands used to set working hours. */
export function wbgtVerdict(value: number): Verdict {
  if (!Number.isFinite(value))
    return { label: "No reading", detail: "No data for this cell.", tone: "low" };
  if (value >= 35)
    return { label: "No work possible", detail: "Beyond every occupational limit.", tone: "critical" };
  if (value >= 32)
    return { label: "Heavy work unsafe", detail: "Only light work, with long rests.", tone: "severe" };
  if (value >= 30)
    return { label: "Rest breaks required", detail: "Heavy outdoor work must be broken up.", tone: "high" };
  if (value >= 28)
    return { label: "Caution", detail: "Manual workers need scheduled water breaks.", tone: "moderate" };
  return { label: "Workable", detail: "Normal outdoor work is safe.", tone: "low" };
}

/** The composed risk index, 0–1. */
export function riskVerdict(value: number): Verdict {
  if (!Number.isFinite(value))
    return { label: "No reading", detail: "No data for this cell.", tone: "low" };
  if (value >= 0.45)
    return { label: "Very high", detail: "Dangerous heat with many people exposed.", tone: "critical" };
  if (value >= 0.3)
    return { label: "High", detail: "Serious heat in a populated area.", tone: "severe" };
  if (value >= 0.15)
    return { label: "Moderate", detail: "Worth watching, especially for vulnerable residents.", tone: "high" };
  if (value > 0.02)
    return { label: "Low", detail: "Some heat load, limited exposure.", tone: "moderate" };
  return { label: "Minimal", detail: "Little or no heat-health risk here.", tone: "low" };
}

export function airTempVerdict(value: number): Verdict {
  if (value >= 45) return { label: "Extreme", detail: "Among the hottest air temperatures recorded here.", tone: "critical" };
  if (value >= 42) return { label: "Very hot", detail: "Well above heatwave thresholds.", tone: "severe" };
  if (value >= 38) return { label: "Hot", detail: "Heatwave territory.", tone: "high" };
  if (value >= 33) return { label: "Warm", detail: "Uncomfortable but ordinary for the season.", tone: "moderate" };
  return { label: "Mild", detail: "Comfortable air temperature.", tone: "low" };
}

export function verdictFor(metric: string, value: number): Verdict {
  switch (metric) {
    case "utci": return utciVerdict(value);
    case "wbgt": return wbgtVerdict(value);
    case "risk": return riskVerdict(value);
    default: return airTempVerdict(value);
  }
}

/** Lower edge of each level, lowest first, matching the verdict functions
 *  above. Used for the map legend, so legend and map can never disagree. */
export const LEVEL_THRESHOLDS: Record<string, number[]> = {
  utci: [-Infinity, 26, 32, 38, 46],
  wbgt: [-Infinity, 28, 30, 32, 35],
  air_temp: [-Infinity, 33, 38, 42, 45],
  risk: [-Infinity, 0.021, 0.15, 0.3, 0.45],
};

export function levelBands(metric: string): { from: number; verdict: Verdict }[] {
  return (LEVEL_THRESHOLDS[metric] ?? LEVEL_THRESHOLDS.utci).map((from) => ({
    from,
    verdict: verdictFor(metric, Number.isFinite(from) ? from : -1e6),
  }));
}

/** "28% above the safe limit" reads; "1.28×" does not. */
export function strainPhrase(ratio: number): string {
  const pct = Math.round(Math.abs(ratio - 1) * 100);
  if (pct < 2) return "right at their safe limit";
  return ratio > 1 ? `${pct}% above their safe limit` : `${pct}% below their safe limit`;
}

/** Turn a 0–1 index into something a person can picture. */
export function densityPhrase(value: number): string {
  if (value >= 0.8) return "very densely built";
  if (value >= 0.6) return "densely built";
  if (value >= 0.4) return "moderately built up";
  if (value >= 0.2) return "lightly built up";
  return "mostly open or green";
}

export function coverPhrase(value: number, kind: "green" | "water"): string {
  // Mass noun, not "parks or greenery": the plural made "a little parks or
  // greenery" ungrammatical in the sentence this feeds.
  const noun = kind === "green" ? "greenery" : "water";
  if (value >= 0.5) return `mostly ${noun}`;
  if (value >= 0.2) return `plenty of ${noun}`;
  if (value >= 0.08) return `some ${noun}`;
  if (value > 0.02) return `a little ${noun}`;
  return `almost no ${noun}`;
}

export function minutesPhrase(minutes: number): string {
  if (minutes >= 60) return "can work the full hour";
  if (minutes <= 0) return "should not work outdoors at all";
  return `can work only ${minutes} minutes per hour`;
}

/**
 * Glossary. One plain sentence per term, surfaced by the `Info` component
 * wherever the term first appears.
 */
export const GLOSSARY: Record<string, string> = {
  UTCI:
    "Universal Thermal Climate Index. It answers 'what does this weather feel like to a human body' by combining heat, humidity, wind and sunshine into one temperature-like number.",
  WBGT:
    "Wet Bulb Globe Temperature. The standard measure used worldwide to decide how long people can safely work outdoors in heat.",
  "Heat Index":
    "The 'feels like' temperature you see in weather apps. It uses only heat and humidity, and ignores wind and sunshine.",
  "Air temperature":
    "What an ordinary thermometer in the shade reads. It is what heatwave warnings are normally based on — and on its own it is a poor guide to danger.",
  "Urban heat island":
    "Cities are hotter than the countryside around them because concrete and asphalt absorb and hold heat while parks and water cool the air.",
  "H3 zone":
    "We divide the city into equal-sized hexagons, each about 0.74 square kilometres — roughly a neighbourhood. Equal size means the numbers are directly comparable.",
  "ISO 7243":
    "The international standard that sets how much heat a worker can safely be exposed to, depending on how hard they are working.",
  ACGIH:
    "A body of occupational-health experts whose published tables say how many minutes per hour someone can work at a given heat level.",
  CAP:
    "Common Alerting Protocol — the international format for public emergency warnings. Speaking it means this system could plug into India's national alerting infrastructure.",
  "Relative risk":
    "How many times more likely a health problem becomes compared with a normal day. A relative risk of 2 means twice as likely.",
  Vulnerability:
    "How badly heat affects the people who live somewhere — driven by age, health, housing and whether they work outdoors.",
  Exposure: "How many people are actually present to be affected.",
  Hazard: "How dangerous the heat itself is, before considering who is there.",
  ERA5:
    "A global record of past weather, rebuilt hour by hour from observations. It lets us replay what the weather actually was on any past date.",
  OpenStreetMap:
    "A free, community-built map of the world. We use it to measure how built-up, green or watered each neighbourhood is.",
};
