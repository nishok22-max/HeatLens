/**
 * Situation summary, computed from the baked data.
 *
 * Everything the Overview states as a fact comes from here. Earlier versions of
 * the Overview carried hardcoded numbers ("14 priority wards", "peak 14:00 -
 * 16:30", "High humidity") that were true of neither dataset. Nothing in this
 * module is a constant about the weather: if a value cannot be derived, it is
 * left out rather than filled in.
 */
import type { HeatData, HexProperties } from "./types";
import { levelBands, utciVerdict, type Verdict } from "./plain";

/** UTCI bands the summary counts against (official thermal-stress bands). */
export const UTCI_VERY_SEVERE = 38;
export const UTCI_SEVERE = 32;

export interface ZoneRank {
  h3: string;
  place: string;
  utci: number;
  verdict: Verdict;
  props: HexProperties;
}

export interface DayOutlook {
  date: string;
  maxUtci: number;
  maxAir: number;
  /** Lowest air temperature of the following night, if the series covers it. */
  nightMin: number | null;
  verdict: Verdict;
  isWorst: boolean;
  isFocus: boolean;
}

export interface Situation {
  /** Hour index (0-23) where the city-mean UTCI peaks on the focus day. */
  peakHour: number;
  peakLabel: string;
  /** Contiguous window around the peak where the city mean stays in the same
   *  band as the peak (at least "severe"); null if the day never gets there. */
  window: { from: string; to: string; hours: number } | null;
  cityMeanPeakUtci: number;
  verdict: Verdict;
  /** Zones at or above "very severe" at the peak hour. */
  zonesVerySevere: number;
  zonesSevere: number;
  nZones: number;
  topZones: ZoneRank[];
  days: DayOutlook[];
  /** Hours between 09:00 and 18:00 a heavy outdoor worker cannot work fully. */
  unsafeWorkHours: number | null;
  workPersonaLabel: string | null;
  /** City-average felt heat and air temperature for each hour of the focus day. */
  hourly: { label: string; utci: number; air: number }[];
  /** How many zones sit in each heat level at the peak hour, lowest level first. */
  levelCounts: { verdict: Verdict; count: number }[];
}

export function placeName(p: HexProperties): string {
  if (!p.place) return `Unnamed zone ${p.h3_index.slice(-4)}`;
  return p.place_exact === false ? `Near ${p.place}` : p.place;
}

export function labelFor(data: HeatData, hour: number): string {
  return data.hourly.meta.labels_ist?.[hour] ?? `${String(hour).padStart(2, "0")}:00`;
}

export function computeSituation(data: HeatData): Situation {
  const cells = data.hexes.features;
  const hours = data.hourly.meta.hours_ist.length || 24;

  const meanUtci: number[] = [];
  for (let h = 0; h < hours; h++) {
    let sum = 0;
    let n = 0;
    for (const f of cells) {
      const v = data.hourly.hexes[f.properties.h3_index]?.utci[h];
      if (Number.isFinite(v)) {
        sum += v;
        n++;
      }
    }
    meanUtci.push(n ? sum / n : NaN);
  }

  const meanAir: number[] = [];
  for (let h = 0; h < hours; h++) {
    let sum = 0;
    let n = 0;
    for (const f of cells) {
      const v = data.hourly.hexes[f.properties.h3_index]?.air_temp[h];
      if (Number.isFinite(v)) {
        sum += v;
        n++;
      }
    }
    meanAir.push(n ? sum / n : NaN);
  }

  let peakHour = 0;
  meanUtci.forEach((v, h) => {
    if (v > meanUtci[peakHour]) peakHour = h;
  });
  const cityMeanPeakUtci = meanUtci[peakHour];
  const verdict = utciVerdict(cityMeanPeakUtci);

  // Window: expand from the peak while the city mean stays at or above the
  // lower edge of the peak's band (never below "severe").
  const floor = cityMeanPeakUtci >= UTCI_VERY_SEVERE ? UTCI_VERY_SEVERE : UTCI_SEVERE;
  let window: Situation["window"] = null;
  if (cityMeanPeakUtci >= UTCI_SEVERE) {
    let a = peakHour;
    let b = peakHour;
    while (a > 0 && meanUtci[a - 1] >= floor) a--;
    while (b < hours - 1 && meanUtci[b + 1] >= floor) b++;
    window = { from: labelFor(data, a), to: labelFor(data, b), hours: b - a + 1 };
  }

  const ranked: ZoneRank[] = cells
    .map((f) => {
      const utci = data.hourly.hexes[f.properties.h3_index]?.utci[peakHour] ?? NaN;
      return {
        h3: f.properties.h3_index,
        place: placeName(f.properties),
        utci,
        verdict: utciVerdict(utci),
        props: f.properties,
      };
    })
    .filter((z) => Number.isFinite(z.utci))
    .sort((x, y) => y.utci - x.utci);

  // One row per place: "Naroda" and "Near Naroda" are the same answer, not two.
  const seen = new Set<string>();
  const topZones = ranked.filter((z) => {
    const key = z.props.place ?? z.h3;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 5);

  return {
    peakHour,
    peakLabel: labelFor(data, peakHour),
    window,
    cityMeanPeakUtci,
    verdict,
    zonesVerySevere: ranked.filter((z) => z.utci >= UTCI_VERY_SEVERE).length,
    zonesSevere: ranked.filter((z) => z.utci >= UTCI_SEVERE).length,
    nZones: cells.length,
    topZones,
    days: dailyOutlook(data),
    ...workLoss(data),
    hourly: meanUtci.map((u, h) => ({
      label: labelFor(data, h),
      utci: Math.round(u * 10) / 10,
      air: Math.round(meanAir[h] * 10) / 10,
    })),
    levelCounts: levelBands("utci").map((band, i, all) => {
      const upper = i + 1 < all.length ? all[i + 1].from : Infinity;
      return {
        verdict: band.verdict,
        count: ranked.filter((z) => z.utci >= band.from && z.utci < upper).length,
      };
    }),
  };
}

/** Group the city-mean series by calendar day. Only whole or daytime-covered
 *  days are returned; a live forecast drops days that are already over. */
function dailyOutlook(data: HeatData): DayOutlook[] {
  const c = data.city;
  const byDate = new Map<string, { utci: number[]; air: number[] }>();
  c.timestamps_ist.forEach((ts, i) => {
    const date = ts.slice(0, 10);
    const hour = Number(ts.slice(11, 13));
    const bucket = byDate.get(date) ?? { utci: [], air: [] };
    // Daytime only for the peak, so a partial first day does not report a
    // 05:30 reading as its "maximum".
    if (hour >= 9 && hour <= 18) {
      bucket.utci.push(c.utci[i]);
      bucket.air.push(c.air_temp[i]);
    }
    byDate.set(date, bucket);
  });

  const nightMin = new Map(c.night_recovery.map((n) => [n.date, n.min_c]));
  // Live mode: a day whose daytime (to 18:00) has already passed is history,
  // not forecast, so it does not belong in "the days ahead".
  const generated = data.meta.mode === "live" ? data.meta.generated_at_ist : undefined;
  const today = generated?.slice(0, 10);
  const todayOver = generated ? Number(generated.slice(11, 13)) >= 18 : false;

  const days = [...byDate.entries()]
    .filter(([date, b]) => b.utci.length >= 6 && (!today || date > today || (date === today && !todayOver)))
    .map(([date, b]) => {
      const maxUtci = Math.max(...b.utci);
      return {
        date,
        maxUtci,
        maxAir: Math.max(...b.air),
        nightMin: nightMin.get(nextDate(date)) ?? nightMin.get(date) ?? null,
        verdict: utciVerdict(maxUtci),
        isWorst: false,
        isFocus: date === data.meta.focus.date,
      };
    });

  if (days.length) {
    const worst = days.reduce((a, b) => (b.maxUtci > a.maxUtci ? b : a));
    worst.isWorst = true;
  }
  return days;
}

function nextDate(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function workLoss(data: HeatData): Pick<Situation, "unsafeWorkHours" | "workPersonaLabel"> {
  const key = data.personas.order.find((k) => k === "construction") ?? data.personas.order[0];
  const p = key ? data.personas.personas[key] : undefined;
  if (!p) return { unsafeWorkHours: null, workPersonaLabel: null };
  const lost = p.safe_minutes_by_hour
    .slice(9, 18)
    .reduce((a, m) => a + (60 - Math.max(0, Math.min(60, m))) / 60, 0);
  return { unsafeWorkHours: lost, workPersonaLabel: p.label };
}

/** "21 May" style date, no locale surprises. */
export function shortDate(date: string): string {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  return `${d} ${months[m - 1]}`;
}

export function weekday(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()] ?? "";
}

/** Source of the weather layer, as declared in provenance. Never hardcoded:
 *  the hindcast uses ERA5 and the live forecast uses Open-Meteo. */
export function weatherSource(data: HeatData): string {
  return data.meta.provenance.find((p) => p.layer === "weather")?.source ?? "weather model";
}
