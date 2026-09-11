import { useLayoutEffect, useRef, useState } from "react";
import {
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HeatData, HourlySeries } from "../types";
import type { Situation } from "../summary";
import { TONE_COLOUR } from "../metrics";
import { levelBands, utciVerdict } from "../plain";

/**
 * "Today at a glance": three small charts under the status headline, each
 * answering one question a non-expert would ask. Every value comes from the
 * Situation summary or the baked personas -- nothing is computed for display
 * that the rest of the page does not also state.
 *
 * Colours: felt heat takes categorical slot 1 (blue) so it stays legible over
 * the warm level bands; the thermometer reading takes slot 2 (orange). Grey
 * was tried and failed the validator's chroma floor. Heat levels reuse the
 * map's level tones, and the work strip uses
 * the reserved status colours, always with a text label beside them.
 */

// Categorical slots 1 and 2, validated as a pair (dataviz validate_palette.js):
// CVD ΔE 24.7, normal-vision ΔE 33.6, both >= 3:1 on the white card.
const FELT = "#2a78d6";
const AIR = "#eb6834";
const AXIS_INK = "#898781";
const BASELINE = "#c3c2b7";
const SURFACE = "#ffffff";

export function HeroCharts({ data, s }: { data: HeatData; s: Situation }) {
  return (
    <div className="mt-5 grid lg:grid-cols-12 gap-3">
      <div className="lg:col-span-8 rounded-xl border border-line p-4">
        <HeatCurve s={s} />
      </div>
      <div className="lg:col-span-4 rounded-xl border border-line p-4">
        <ZoneLevels s={s} />
      </div>
      <div className="lg:col-span-12 rounded-xl border border-line p-4">
        <WorkStrip data={data} />
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 1 ---- */

function HeatCurve({ s }: { s: Situation }) {
  const rows = s.hourly.filter((r) => Number.isFinite(r.utci) && Number.isFinite(r.air));
  if (!rows.length) return null;
  const values = rows.flatMap((r) => [r.utci, r.air]);
  const lo = Math.floor(Math.min(...values) - 2);
  const hi = Math.ceil(Math.max(...values) + 2);

  const bands = levelBands("utci")
    .map((b, i, all) => ({
      from: Math.max(Number.isFinite(b.from) ? b.from : lo, lo),
      to: Math.min(i + 1 < all.length ? all[i + 1].from : hi, hi),
      verdict: b.verdict,
    }))
    .filter((b) => b.to > b.from);

  const peak = s.hourly[s.peakHour];
  const gap = peak ? peak.utci - peak.air : NaN;

  return (
    <figure>
      <figcaption>
        <h3 className="text-[15px] font-semibold text-ink">When is it dangerous?</h3>
        <p className="text-[13px] text-ink-soft">
          City average through the day. The coloured bands are the heat levels used on the map.
        </p>
      </figcaption>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-soft">
        <LineKey colour={FELT} label="How hot it feels to the body (UTCI)" />
        <LineKey colour={AIR} label="What a thermometer reads (air temperature)" />
      </div>

      <div className="h-60 mt-2" role="img" aria-label={curveSummary(s)}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 22, right: 8, left: -8, bottom: 0 }}>
            {bands.map((b) => (
              <ReferenceArea
                key={b.verdict.label}
                y1={b.from}
                y2={b.to}
                fill={TONE_COLOUR[b.verdict.tone].bg}
                fillOpacity={0.3}
                stroke="none"
                ifOverflow="hidden"
                label={{
                  value: b.verdict.label,
                  position: "insideTopRight",
                  fill: "#52514e",
                  fontSize: 11,
                }}
              />
            ))}
            <XAxis
              dataKey="label"
              interval={2}
              tick={{ fontSize: 11, fill: AXIS_INK }}
              tickLine={false}
              axisLine={{ stroke: BASELINE }}
            />
            <YAxis
              domain={[lo, hi]}
              allowDecimals={false}
              tickFormatter={(v: number) => `${v}°`}
              tick={{ fontSize: 11, fill: AXIS_INK }}
              tickLine={false}
              axisLine={false}
              width={40}
            />
            <Tooltip content={<CurveTip />} cursor={{ stroke: "#52514e", strokeWidth: 1 }} />
            <Line
              dataKey="air"
              stroke={AIR}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: AIR, stroke: SURFACE, strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="utci"
              stroke={FELT}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: FELT, stroke: SURFACE, strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {peak && (
              <ReferenceDot
                x={peak.label}
                y={peak.utci}
                r={5}
                fill={FELT}
                stroke={SURFACE}
                strokeWidth={2}
                label={{
                  value: `Peak ${peak.utci.toFixed(1)} °C at ${peak.label}`,
                  position: "top",
                  fontSize: 12,
                  fill: "#0b0b0b",
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {Number.isFinite(gap) && gap > 0.5 && (
        <p className="mt-2 text-[13px] text-ink">
          At the peak, the body feels <strong className="font-semibold">{gap.toFixed(1)} °C more</strong> than
          the thermometer shows. That gap is the sun and humidity, and it is why HeatLens does not
          use temperature alone.
        </p>
      )}
    </figure>
  );
}

function curveSummary(s: Situation): string {
  const p = s.hourly[s.peakHour];
  return p
    ? `City-average felt heat peaks at ${p.utci.toFixed(1)} °C at ${p.label}, when air temperature is ${p.air.toFixed(1)} °C.`
    : "City-average heat through the day.";
}

function CurveTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: number | string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const felt = Number(payload.find((p) => p.dataKey === "utci")?.value);
  const air = Number(payload.find((p) => p.dataKey === "air")?.value);
  const v = utciVerdict(felt);
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-md text-[12px]">
      <div className="font-semibold text-ink">{label}</div>
      <div className="flex items-center gap-2 mt-1 text-ink">
        <span className="inline-block w-3 h-0.5" style={{ background: FELT }} aria-hidden />
        Feels like {felt.toFixed(1)} °C · {v.label}
      </div>
      <div className="flex items-center gap-2 text-ink-soft">
        <span className="inline-block w-3 h-0.5" style={{ background: AIR }} aria-hidden />
        Thermometer {air.toFixed(1)} °C
      </div>
    </div>
  );
}

/** One zone through the day: same encoding as the city curve above, sized
 *  for the zone panel, with the map's current hour marked so the chart and
 *  the map always agree on "when". */
export function ZoneDayCurve({
  series,
  labels,
  hour,
  height = 150,
}: {
  series: HourlySeries;
  labels: string[];
  hour: number;
  height?: number;
}) {
  const rows = series.utci
    .map((u, i) => ({ label: labels[i] ?? `${i}`, utci: u, air: series.air_temp[i] }))
    .filter((r) => Number.isFinite(r.utci) && Number.isFinite(r.air));
  if (!rows.length) return null;
  const values = rows.flatMap((r) => [r.utci, r.air]);
  const lo = Math.floor(Math.min(...values) - 2);
  const hi = Math.ceil(Math.max(...values) + 2);
  const bands = levelBands("utci")
    .map((b, i, all) => ({
      from: Math.max(Number.isFinite(b.from) ? b.from : lo, lo),
      to: Math.min(i + 1 < all.length ? all[i + 1].from : hi, hi),
      verdict: b.verdict,
    }))
    .filter((b) => b.to > b.from);
  const peak = rows.reduce((a, b) => (b.utci > a.utci ? b : a));
  const now = rows[hour];

  return (
    <div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-soft">
        <LineKey colour={FELT} label="Feels like (UTCI)" />
        <LineKey colour={AIR} label="Thermometer (air)" />
      </div>
      <div style={{ height }} className="mt-1" role="img"
        aria-label={`Felt heat here peaks at ${peak.utci.toFixed(1)} °C at ${peak.label}.`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 18, right: 6, left: -14, bottom: 0 }}>
            {bands.map((b) => (
              <ReferenceArea key={b.verdict.label} y1={b.from} y2={b.to}
                fill={TONE_COLOUR[b.verdict.tone].bg} fillOpacity={0.3} stroke="none" ifOverflow="hidden" />
            ))}
            <XAxis dataKey="label" interval={3} tick={{ fontSize: 10, fill: AXIS_INK }}
              tickLine={false} axisLine={{ stroke: BASELINE }} />
            <YAxis domain={[lo, hi]} allowDecimals={false} tickFormatter={(v: number) => `${v}°`}
              tick={{ fontSize: 10, fill: AXIS_INK }} tickLine={false} axisLine={false} width={38} />
            <Tooltip content={<CurveTip />} cursor={{ stroke: "#52514e", strokeWidth: 1 }} />
            {now && (
              <ReferenceLine x={now.label} stroke="#52514e" strokeWidth={1}
                label={{ value: "map hour", position: "insideTopLeft", fontSize: 10, fill: "#52514e" }} />
            )}
            <Line dataKey="air" stroke={AIR} strokeWidth={2} dot={false}
              activeDot={{ r: 4, fill: AIR, stroke: SURFACE, strokeWidth: 2 }} isAnimationActive={false} />
            <Line dataKey="utci" stroke={FELT} strokeWidth={2} dot={false}
              activeDot={{ r: 4, fill: FELT, stroke: SURFACE, strokeWidth: 2 }} isAnimationActive={false} />
            <ReferenceDot x={peak.label} y={peak.utci} r={4} fill={FELT} stroke={SURFACE} strokeWidth={2}
              label={{ value: `${peak.utci.toFixed(1)} °C`, position: "top", fontSize: 11, fill: "#0b0b0b" }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function LineKey({ colour, label }: { colour: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block w-4 h-0.5 rounded-full" style={{ background: colour }} aria-hidden />
      {label}
    </span>
  );
}

/* ---------------------------------------------------------------- 2 ---- */

/** Narrowest segment, in pixels, that holds a three-digit count with padding. */
const MIN_LABEL_PX = 28;

function ZoneLevels({ s }: { s: Situation }) {
  const [hover, setHover] = useState<number | null>(null);
  const segments = s.levelCounts.filter((c) => c.count > 0);
  const total = segments.reduce((a, c) => a + c.count, 0) || 1;
  const active = hover !== null ? segments[hover] : null;

  // Measure the bar, then decide per segment whether its count fits. A
  // percentage threshold guesses; the rendered width is the actual constraint.
  const barRef = useRef<HTMLDivElement>(null);
  const [barPx, setBarPx] = useState(0);
  useLayoutEffect(() => {
    const el = barRef.current;
    if (!el) return;
    const measure = () => setBarPx(el.getBoundingClientRect().width);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const gaps = Math.max(0, segments.length - 1) * 2;

  return (
    <figure>
      <figcaption>
        <h3 className="text-[15px] font-semibold text-ink">How much of the city?</h3>
        <p className="text-[13px] text-ink-soft">
          All {s.nZones} neighbourhood zones by heat level at {s.peakLabel}
        </p>
      </figcaption>

      <div ref={barRef} className="mt-4 flex h-8 gap-[2px]" onMouseLeave={() => setHover(null)}>
        {segments.map((c, i) => {
          const pct = (c.count / total) * 100;
          const tone = TONE_COLOUR[c.verdict.tone];
          return (
            <div
              key={c.verdict.label}
              tabIndex={0}
              role="img"
              aria-label={`${c.verdict.label}: ${c.count} zones, ${Math.round(pct)}%`}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              className={`min-w-[6px] grid place-items-center text-[12px] font-semibold cursor-default ${
                i === 0 ? "rounded-l" : ""
              } ${i === segments.length - 1 ? "rounded-r" : ""}`}
              style={{ flexGrow: c.count, flexBasis: 0, background: tone.bg, color: tone.ink }}
            >
              {/* Label only when the measured segment can hold it; narrower
                  slivers rely on the legend and the hover line below. */}
              {((barPx - gaps) * pct) / 100 >= MIN_LABEL_PX ? c.count : ""}
            </div>
          );
        })}
      </div>

      <div className="h-5 mt-1 text-[12px] text-ink-soft" aria-live="polite">
        {active
          ? `${active.verdict.label}: ${active.count} zones (${Math.round((active.count / total) * 100)}%)`
          : ""}
      </div>

      <ul className="mt-1 space-y-1">
        {s.levelCounts
          .slice()
          .reverse()
          .map((c) => (
            <li key={c.verdict.label} className="flex items-center gap-2 text-[13px]">
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ background: TONE_COLOUR[c.verdict.tone].bg }}
                aria-hidden
              />
              <span className="flex-1 text-ink">{c.verdict.label}</span>
              <span className="text-ink tnum">{c.count}</span>
              <span className="w-10 text-right text-ink-faint tnum">
                {Math.round((c.count / total) * 100)}%
              </span>
            </li>
          ))}
      </ul>
    </figure>
  );
}

/* ---------------------------------------------------------------- 3 ---- */

/** Reserved status colours (dataviz palette), each always shown with its label. */
const WORK_STATUS = [
  { min: 60, label: "Full hour of work", bg: "#0ca30c", ink: "#ffffff" },
  { min: 30, label: "Limited: rest breaks needed", bg: "#fab219", ink: "#0b0b0b" },
  { min: 1, label: "Mostly unsafe", bg: "#ec835a", ink: "#0b0b0b" },
  { min: 0, label: "No safe work", bg: "#d03b3b", ink: "#ffffff" },
] as const;

export function statusFor(minutes: number) {
  return WORK_STATUS.find((st) => minutes >= st.min) ?? WORK_STATUS[WORK_STATUS.length - 1];
}

function WorkStrip({ data }: { data: HeatData }) {
  const [hover, setHover] = useState<number | null>(null);
  const key = data.personas.order.includes("construction") ? "construction" : data.personas.order[0];
  const persona = key ? data.personas.personas[key] : undefined;
  if (!persona) return null;
  const labels = data.hourly.meta.labels_ist ?? [];
  const minutes = persona.safe_minutes_by_hour.map((m) => Math.max(0, Math.min(60, m)));
  const full = minutes.filter((m) => m >= 60).length;
  const none = minutes.filter((m) => m <= 0).length;
  const h = hover !== null ? hover : null;

  return (
    <figure>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-[15px] font-semibold text-ink">When can people work outside?</h3>
          <p className="text-[13px] text-ink-soft">
            {persona.label}: safe minutes of work in each hour (ISO 7243 and ACGIH limits)
          </p>
        </div>
        <p className="text-[13px] text-ink">
          <strong className="font-semibold">{full}</strong> full hours ·{" "}
          <strong className="font-semibold">{none}</strong> hours with no safe work
        </p>
      </figcaption>

      <div
        className="mt-3 grid gap-[2px]"
        style={{ gridTemplateColumns: `repeat(${minutes.length}, minmax(0, 1fr))` }}
        onMouseLeave={() => setHover(null)}
      >
        {minutes.map((m, i) => {
          const st = statusFor(m);
          return (
            <div
              key={i}
              tabIndex={0}
              role="img"
              aria-label={`${labels[i] ?? i}: ${m} safe minutes, ${st.label}`}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              className={`h-9 grid place-items-center text-[11px] font-semibold cursor-default ${
                i === 0 ? "rounded-l" : ""
              } ${i === minutes.length - 1 ? "rounded-r" : ""} ${hover === i ? "ring-2 ring-ink ring-offset-1" : ""}`}
              style={{ background: st.bg, color: st.ink }}
            >
              <span className="hidden md:inline">{m}</span>
            </div>
          );
        })}
      </div>
      <div
        className="grid mt-1 text-[11px] text-ink-faint tnum"
        style={{ gridTemplateColumns: `repeat(${minutes.length}, minmax(0, 1fr))` }}
        aria-hidden
      >
        {minutes.map((_, i) => (
          <span key={i} className="text-center">
            {i % 3 === 0 ? (labels[i] ?? "").slice(0, 2) : ""}
          </span>
        ))}
      </div>

      <div className="h-5 mt-1 text-[12px] text-ink-soft" aria-live="polite">
        {h !== null
          ? `${labels[h] ?? h}: ${minutes[h]} safe minutes per hour · ${statusFor(minutes[h]).label}`
          : "Hover or tab to an hour for details. Numbers are safe minutes out of 60."}
      </div>

      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-soft">
        {WORK_STATUS.map((st) => (
          <li key={st.label} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: st.bg }} aria-hidden />
            {st.label}
          </li>
        ))}
      </ul>
    </figure>
  );
}
