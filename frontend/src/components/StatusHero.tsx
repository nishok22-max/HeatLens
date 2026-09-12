import type { HeatData } from "../types";
import type { Situation } from "../summary";
import { shortDate, weekday, weatherSource } from "../summary";
import type { ViewKey } from "./AppShell";
import { LevelChip } from "./ui";
import { HeroCharts } from "./HeroCharts";
import { Info } from "./Info";

export type Role = "commissioner" | "health" | "labour" | "resident";

export const ROLES: { key: Role; label: string }[] = [
  { key: "commissioner", label: "City commissioner" },
  { key: "health", label: "Health officer" },
  { key: "labour", label: "Labour inspector" },
  { key: "resident", label: "Residents" },
];

/**
 * The first thing on the page: how bad, when, where, and what to do.
 * Every figure comes from `computeSituation` - nothing here is typed in.
 */
export function StatusHero({
  data,
  s,
  role,
  onRole,
  onNavigate,
}: {
  data: HeatData;
  s: Situation;
  role: Role;
  onRole: (r: Role) => void;
  onNavigate: (v: ViewKey) => void;
}) {
  const isLive = data.meta.mode === "live";
  const focus = data.meta.focus.date;
  // The pipeline picks the focus day by worker heat stress (WBGT) ahead, not by
  // felt heat, so the label says exactly that (live.py: focus_idx).
  const eyebrow = isLive
    ? `Live forecast · showing the worst day ahead for outdoor work`
    : `Replay of ${shortDate(focus)} 2010 · rebuilt from ${weatherSource(data)} weather records`;
  const day = isLive ? ` on ${weekday(focus)} ${shortDate(focus)}` : "";

  const when = s.window && s.window.hours > 1
    ? `${day}, peaking at ${s.peakLabel} (${s.window.from} to ${s.window.to})`
    : `${day}, peaking at ${s.peakLabel}`;

  const zoneCount = s.zonesVerySevere > 0 ? s.zonesVerySevere : s.zonesSevere;
  const zoneBand = s.zonesVerySevere > 0 ? "very severe or worse" : "severe or worse";
  const hottest = s.topZones[0];

  const stats = [
    {
      value: `${zoneCount} of ${s.nZones}`,
      label: `neighbourhood zones at ${zoneBand} heat at ${s.peakLabel}`,
    },
    hottest && {
      value: hottest.place,
      label: `hottest area · feels like ${hottest.utci.toFixed(1)} °C`,
    },
    s.unsafeWorkHours !== null && {
      value: `${s.unsafeWorkHours.toFixed(1)} h`,
      label: `of a 9-to-6 shift unsafe for ${s.workPersonaLabel?.toLowerCase() ?? "outdoor workers"}`,
    },
    {
      value: `${data.meta.kill_gate.utci_spread_c.toFixed(1)} °C`,
      label: "difference in felt heat between neighbourhoods",
    },
  ].filter(Boolean) as { value: string; label: string }[];

  return (
    <section className="card overflow-hidden" aria-labelledby="status-heading">
      <div className="p-5 lg:p-7">
        <p className="text-[13px] text-ink-soft">{eyebrow}</p>

        <div className="mt-2 flex flex-wrap items-center gap-3">
          <LevelChip verdict={s.verdict} size="lg" />
          <h2 id="status-heading" className="text-[24px] lg:text-[30px] font-bold text-ink leading-tight tracking-tight">
            {s.verdict.label} heat stress in {data.meta.city}{when}
          </h2>
        </div>
        <p className="mt-2 text-[15px] text-ink-soft max-w-3xl">
          {s.verdict.detail}{" "}
          <span className="text-ink-faint">
            City average{" "}
            <Info term="UTCI" label="feels-like heat" /> peaks at{" "}
            {s.cityMeanPeakUtci.toFixed(1)} °C.
          </span>
        </p>

        <dl className="mt-5 grid grid-cols-2 lg:grid-cols-4 gap-3">
          {stats.map((st) => (
            <div key={st.label} className="rounded-xl bg-sunken/60 border border-line px-4 py-3">
              <dt className="sr-only">{st.label}</dt>
              <dd className="text-[20px] lg:text-[22px] font-bold text-ink tnum leading-tight break-words">
                {st.value}
              </dd>
              <dd className="text-[12px] text-ink-soft leading-snug mt-0.5">{st.label}</dd>
            </div>
          ))}
        </dl>

        <HeroCharts data={data} s={s} />
      </div>

      <div className="border-t border-line bg-sunken/40 px-5 lg:px-7 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-[16px] font-bold text-ink">What to do now</h3>
          <div role="tablist" aria-label="Show actions for" className="flex flex-wrap gap-1 bg-surface p-1 rounded-lg border border-line no-print">
            {ROLES.map((r) => (
              <button
                key={r.key}
                role="tab"
                aria-selected={role === r.key}
                onClick={() => onRole(r.key)}
                className={`px-3 py-1.5 rounded-md text-[13px] transition-colors ${
                  role === r.key ? "bg-ink text-white font-semibold" : "text-ink-soft hover:text-ink hover:bg-sunken"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4">
          <RoleActions data={data} s={s} role={role} onNavigate={onNavigate} />
        </div>
      </div>
    </section>
  );
}

function RoleActions({
  data,
  s,
  role,
  onNavigate,
}: {
  data: HeatData;
  s: Situation;
  role: Role;
  onNavigate: (v: ViewKey) => void;
}) {
  const places = s.topZones.slice(0, 3).map((z) => z.place).join(", ");

  if (role === "commissioner") {
    const actions = data.insights.actions.slice(0, 3);
    return (
      <>
        <ol className="grid md:grid-cols-3 gap-3">
          {actions.map((a, i) => (
            <li key={a.title} className="rounded-xl bg-surface border border-line p-4">
              <span className="text-[12px] font-semibold text-accent">Step {i + 1}</span>
              <p className="text-[15px] font-semibold text-ink leading-snug mt-0.5">{a.title}</p>
              <p className="text-[13px] text-ink-soft leading-snug mt-1">{a.detail}</p>
            </li>
          ))}
        </ol>
        <NavLink onClick={() => onNavigate("scenarios")}>Compare interventions</NavLink>
      </>
    );
  }

  if (role === "health") {
    return (
      <>
        <ul className="space-y-2 text-[15px] text-ink">
          <li>
            <strong>Prepare for the peak:</strong>{" "}
            {s.window ? `${s.window.from} to ${s.window.to}` : `around ${s.peakLabel}`} on {shortDate(data.meta.focus.date)}.
          </li>
          {places && (
            <li>
              <strong>Prioritise:</strong> {places}.
            </li>
          )}
          <li>
            <strong>Public message:</strong> “{data.advisory.text.en}”
          </li>
        </ul>
      </>
    );
  }

  if (role === "labour") {
    const shift = data.insights.scenarios.find((x) => x.key === "shift_hours");
    return (
      <>
        <ul className="space-y-2 text-[15px] text-ink">
          {data.personas.order
            .filter((k) => k === "construction" || k === "delivery")
            .map((k) => {
              const p = data.personas.personas[k];
              const labels = data.hourly.meta.labels_ist ?? [];
              const full = p.full_capacity_hours.map((h) => labels[h] ?? `${h}:00`);
              return (
                <li key={k}>
                  <strong>{p.label}:</strong>{" "}
                  {full.length === 0
                    ? "no hour of this day allows full-capacity outdoor work."
                    : `full-capacity work only at ${summariseHours(full)}.`}
                </li>
              );
            })}
          {shift && shift.reduction_pct !== undefined && (
            <li>
              <strong>{shift.label}:</strong> {shift.detail} Unsafe work hours drop from{" "}
              {shift.unsafe_before} to {shift.unsafe_after} ({shift.reduction_pct}% fewer).
            </li>
          )}
        </ul>
        <NavLink onClick={() => onNavigate("work")}>Open the hour-by-hour work grid</NavLink>
      </>
    );
  }

  return (
    <>
      <p className="text-[17px] text-ink leading-relaxed max-w-3xl">“{data.advisory.text.en}”</p>
      <p className="text-[13px] text-ink-soft mt-2">
        Also available in Hindi and Gujarati (draft translations, awaiting review by a native speaker).
      </p>
      <NavLink onClick={() => onNavigate("map")}>Check your neighbourhood</NavLink>
    </>
  );
}

function NavLink({ onClick, children }: { onClick: () => void; children: string }) {
  return (
    <button onClick={onClick} className="mt-4 text-[14px] font-semibold text-accent hover:underline no-print">
      {children} →
    </button>
  );
}

/** "06:30, 07:30, 08:30" -> "06:30-08:30". Keeps a long list readable. */
function summariseHours(labels: string[]): string {
  if (labels.length <= 3) return labels.join(", ");
  return `${labels.length} hours (${labels[0]} to ${labels[labels.length - 1]})`;
}
