import type { ReactNode } from "react";
import type { HeatData } from "../types";
import { METRICS, TONE_COLOUR, formatValue } from "../metrics";
import {
  coverPhrase,
  densityPhrase,
  minutesPhrase,
  strainPhrase,
  verdictFor,
} from "../plain";
import { LevelChip } from "./ui";
import { Info } from "./Info";
import { ZoneDayCurve, statusFor } from "./HeroCharts";

/**
 * One neighbourhood, as pictures first and words second.
 *
 * Every fact the old text panel carried is still here -- the four measures and
 * their levels, relative risk and its caveat, the offset from the city mean,
 * land cover, each persona's strain and safe minutes, the worst hour and the
 * action -- but each is drawn: tiles, a day curve, a diverging scale, bars and
 * meters, each with its words beside it so nothing depends on colour alone.
 *
 * Uses a container query, so it lays out in two columns when its panel is wide
 * (the heat-map page) and one when narrow (the work-safety page).
 */

const SEVERITY_LABEL = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  critical: "Critical",
} as const;
type Severity = keyof typeof SEVERITY_LABEL;

/** Diverging pair from the dataviz palette: red = hotter, blue = cooler. */
const HOTTER = "#e34948";
const COOLER = "#2a78d6";
const BAR = "#52514e";

export function CellDetail({
  data,
  h3,
  hour,
  onClose,
}: {
  data: HeatData;
  h3: string | null;
  hour: number;
  onClose: () => void;
}) {
  if (!h3) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center min-h-64 bg-surface/50">
        <h3 className="text-[16px] font-semibold text-ink mb-1">Pick a neighbourhood</h3>
        <p className="text-[13px] text-ink-soft leading-relaxed max-w-xs">
          Click any hexagon on the map to see how hot it gets there, why, who is at risk, and what to do.
        </p>
      </div>
    );
  }

  const feature = data.hexes.features.find((f) => f.properties.h3_index === h3);
  const series = data.hourly.hexes[h3];
  if (!feature || !series) return null;

  const p = feature.properties;
  const labels = data.hourly.meta.labels_ist ?? [];
  const label = labels[hour] ?? `${hour}:00`;
  const utci = series.utci[hour];
  const wbgt = series.wbgt[hour];
  const felt = verdictFor("utci", utci);
  const feltPeak = series.utci.reduce((best, v, i) => (v > series.utci[best] ? i : best), 0);
  const action = zoneAction(series.utci, labels);

  return (
    <div className="@container bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 bg-slate-900 text-white">
        <div className="min-w-0">
          <div className="text-[12px] text-slate-300">
            {p.place ? (p.place_exact ? "Zone" : "Zone near") : "Zone"}{" "}
            <span className="font-mono text-slate-400">#{h3.slice(-6)}</span>
          </div>
          <div className="text-[18px] font-bold leading-tight truncate">{p.place ?? "Unnamed area"}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <LevelChip verdict={felt} />
          <button
            onClick={onClose}
            className="no-print text-[12px] text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-md px-2.5 py-1"
          >
            Close
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Wide panel: [how hot + when] | [why + who], action underneath. */}
        <div className="grid @lg:grid-cols-2 gap-4 items-start">
        <div className="space-y-4">
        {/* 1 — How hot */}
        <Block n={1} title="How hot is it here?" sub={`At ${label}. ${felt.detail}`}>
          <div className="grid grid-cols-2 gap-2">
            {(["utci", "wbgt", "air_temp", "risk"] as const).map((key) => {
              const def = METRICS[key];
              const value = series[key][hour];
              const v = verdictFor(key, value);
              return (
                <div key={key} className="rounded-lg border border-line overflow-hidden">
                  <div className="h-1.5" style={{ background: TONE_COLOUR[v.tone].bg }} aria-hidden />
                  <div className="p-2.5">
                    <div className="text-[12px] text-ink-soft leading-tight">
                      {key === "risk" ? (
                        <Info term="Relative risk" label="Relative health risk" />
                      ) : (
                        def.plain
                      )}
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 mt-0.5">
                      <span className="text-[18px] font-bold text-ink leading-tight">{formatValue(value, def)}</span>
                      <LevelChip verdict={v} />
                    </div>
                    {key === "risk" && (
                      <div className="text-[11px] text-ink-faint mt-1">relative · not calibrated</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Block>

        {/* 2 — When */}
        <Block
          n={2}
          title="When is it worst?"
          sub={`Felt heat peaks at ${labels[feltPeak] ?? feltPeak} · worst for outdoor work (WBGT) at ${labels[p.peak_hour] ?? p.peak_hour}`}
        >
          <ZoneDayCurve series={series} labels={labels} hour={hour} height={110} />
        </Block>

        {/* 5 — What (in the left column so the two columns balance) */}
        <Block n={5} title="What should be done here?" sub="From this zone's own hourly heat">
          <div className="bg-teal-soft/60 border border-teal/30 p-3 rounded-lg">
            <p className="text-[14px] text-ink leading-snug">{action}</p>
          </div>
        </Block>
        </div>

        <div className="space-y-4">
          {/* 3 — Why */}
          <Block n={3} title="Why is it hot here?" sub="Compared with the rest of the city">
            <OffsetScale d={p.d_ta_c} />
            {/* Green and water are shown as bars below; the full wording stays
                available on hover so nothing the old text said is lost. */}
            <p
              className="text-[13px] text-ink-soft mt-2 leading-snug"
              title={`${capitalise(densityPhrase(p.intensity))}, with ${coverPhrase(p.green, "green")} and ${coverPhrase(p.water, "water")}.`}
            >
              {capitalise(densityPhrase(p.intensity))}. Built-up areas hold heat (
              <Info term="Urban heat island" label="urban heat island" />).
            </p>
            <ul className="mt-2 space-y-1.5">
              <CoverBar label="Built-up density" value={p.intensity} />
              <CoverBar label="Road coverage" value={p.roads} />
              <CoverBar label="Parks and greenery" value={p.green} />
              <CoverBar label="Water" value={p.water} />
            </ul>
          </Block>

          {/* 4 — Who */}
          <Block n={4} title="Who is at risk?" sub={`Safe minutes of outdoor work per hour at ${label}`}>
            <ul className="space-y-2.5">
              {data.personas.order.map((key) => {
                const persona = data.personas.personas[key];
                const minutes = clampMinutes(persona.safe_minutes_by_hour[hour]);
                const ratio = wbgt / persona.limit_c;
                const severity = severityFor(ratio);
                const st = statusFor(minutes);
                const tone = TONE_COLOUR[severity];
                return (
                  <li key={key}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-semibold text-ink leading-tight">{persona.label}</span>
                      <span
                        className="text-[11px] font-semibold rounded px-1.5 py-0.5 shrink-0"
                        style={{ background: tone.bg, color: tone.ink }}
                      >
                        {SEVERITY_LABEL[severity]}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <div
                        className="flex-1 h-2.5 rounded-full bg-sunken overflow-hidden"
                        role="img"
                        aria-label={`${minutes} of 60 safe minutes`}
                      >
                        <div className="h-full rounded-full" style={{ width: `${(minutes / 60) * 100}%`, background: st.bg }} />
                      </div>
                      <span className="text-[12px] text-ink tnum whitespace-nowrap">
                        {minutes} / 60 · {st.label}
                      </span>
                    </div>
                    {/* The meter says how many minutes; the text adds the two
                        things it cannot: distance from the limit, and why the
                        limit is lower for this person. */}
                    <p className="text-[12px] text-ink-soft leading-snug mt-0.5" title={minutesPhrase(minutes)}>
                      {capitalise(strainPhrase(ratio))}.
                      {persona.vulnerability_offset_c > 0 &&
                        ` Limit lowered ${persona.vulnerability_offset_c.toFixed(1)} °C for age or health.`}
                    </p>
                  </li>
                );
              })}
            </ul>
          </Block>
        </div>
        </div>
      </div>
    </div>
  );
}

function Block({ n, title, sub, children }: { n: number; title: string; sub: string; children: ReactNode }) {
  return (
    <section>
      <div className="flex items-baseline gap-2">
        <span className="w-5 h-5 rounded-full bg-ink text-white text-[11px] font-semibold grid place-items-center shrink-0 self-center">
          {n}
        </span>
        <h4 className="text-[15px] font-semibold text-ink">{title}</h4>
      </div>
      <p className="text-[12px] text-ink-faint pl-7 mb-2 leading-snug">{sub}</p>
      {children}
    </section>
  );
}

/** Hotter or cooler than the city mean, on a centred scale. */
function OffsetScale({ d }: { d: number }) {
  const range = Math.max(2, Math.ceil(Math.abs(d)));
  const half = (Math.abs(d) / range) * 50;
  const hotter = d >= 0;
  return (
    <div>
      <div className="text-[13px] text-ink">
        <strong className="font-semibold">
          {hotter ? "+" : "−"}
          {Math.abs(d).toFixed(2)} °C
        </strong>{" "}
        {hotter ? "hotter" : "cooler"} than the city average
      </div>
      <div
        className="relative h-3 mt-1.5 rounded-full bg-sunken"
        role="img"
        aria-label={`${Math.abs(d).toFixed(2)} degrees ${hotter ? "hotter" : "cooler"} than the city average`}
      >
        <div
          className="absolute top-0 h-full rounded-full"
          style={{
            left: hotter ? "50%" : `${50 - half}%`,
            width: `${half}%`,
            background: hotter ? HOTTER : COOLER,
          }}
        />
        <div className="absolute top-[-3px] bottom-[-3px] left-1/2 w-px bg-ink" aria-hidden />
      </div>
      <div className="flex justify-between text-[11px] text-ink-faint mt-0.5 tnum">
        <span>−{range} °C cooler</span>
        <span>city average</span>
        <span>+{range} °C hotter</span>
      </div>
    </div>
  );
}

function CoverBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <li className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-[12px]">
      <span className="text-ink-soft">{label}</span>
      <span className="h-2 rounded-full bg-sunken overflow-hidden" aria-hidden>
        <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: BAR }} />
      </span>
      <span className="text-ink tnum text-right">{pct}%</span>
    </li>
  );
}

function capitalise(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

/** A zone-specific instruction built from the zone's own hourly UTCI, replacing
 *  a sentence that gave every zone the same hardcoded "12:00 and 16:30". */
function zoneAction(utci: number[], labels: string[]): string {
  const span = (min: number) => {
    const hrs = utci.map((v, i) => (v >= min ? i : -1)).filter((i) => i >= 0);
    return hrs.length ? { from: labels[hrs[0]] ?? `${hrs[0]}:00`, to: labels[hrs[hrs.length - 1]] ?? "", n: hrs.length } : null;
  };
  const verySevere = span(38);
  if (verySevere) {
    return `Stop heavy outdoor work and set up shade and drinking-water points between ${verySevere.from} and ${verySevere.to} (${verySevere.n} h at very severe heat or worse).`;
  }
  const severe = span(32);
  if (severe) {
    return `Schedule rest breaks and water for outdoor workers between ${severe.from} and ${severe.to} (${severe.n} h at severe heat).`;
  }
  return "No hour reaches severe heat stress here on this day. Routine precautions only.";
}

function clampMinutes(value: number | undefined): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(60, value as number)) : 0;
}

function severityFor(ratio: number): Severity {
  if (ratio >= 1.15) return "critical";
  if (ratio >= 1.0) return "severe";
  if (ratio >= 0.9) return "high";
  if (ratio >= 0.75) return "moderate";
  return "low";
}
