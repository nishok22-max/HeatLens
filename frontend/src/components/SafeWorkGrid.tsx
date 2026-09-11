import type { HeatData } from "../types";
import { Badge, Note, Panel } from "./ui";

function swatch(minutes: number): { bg: string; ink: string } {
  if (minutes >= 60) return { bg: "#dcfce7", ink: "#14532d" };
  if (minutes >= 45) return { bg: "#fef3c7", ink: "#78350f" };
  if (minutes >= 30) return { bg: "#ffedd5", ink: "#7c2d12" };
  if (minutes > 0) return { bg: "#fee2e2", ink: "#991b1b" };
  return { bg: "#701a75", ink: "#ffffff" };
}

export function SafeWorkGrid({
  data,
  hour,
  onHour,
}: {
  data: HeatData;
  hour: number;
  onHour: (h: number) => void;
}) {
  const labels = data.hourly.meta.labels_ist ?? [];
  const hours = data.hourly.meta.hours_ist;

  const blockedHours = hours.filter((_, i) =>
    data.personas.order.every(
      (k) => data.personas.personas[k].safe_minutes_by_hour[i] === 0,
    ),
  );

  const longestRun = hours.reduce(
    (acc, _, i) => {
      const blocked = data.personas.order.every(
        (k) => data.personas.personas[k].safe_minutes_by_hour[i] === 0,
      );
      const run = blocked ? acc.run + 1 : 0;
      return { run, best: Math.max(acc.best, run) };
    },
    { run: 0, best: 0 },
  ).best;

  const heavy = data.personas.personas.construction;

  return (
    <Panel
      title="Safe outdoor work, hour by hour"
      subtitle={`Minutes per hour each group can safely work outdoors · ${data.personas.date}`}
      right={
        <div className="text-right bg-flag-bg border border-flag/30 px-3.5 py-1.5 rounded-xl shadow-2xs">
          <div className="text-[22px] font-black tnum leading-none text-flag">
            {blockedHours.length} h
          </div>
          <div className="text-[10px] uppercase font-black tracking-wider text-flag/90 mt-0.5">
            Unsafe for all personas
          </div>
        </div>
      }
    >
      <div className="overflow-x-auto rounded-xl border border-line shadow-2xs">
        <table className="w-full border-collapse bg-surface">
          <thead>
            <tr className="bg-sunken/60 border-b border-line">
              <th className="text-left text-[10px] uppercase font-black tracking-wider text-ink-faint py-3 px-3.5 w-60">
                Persona / Labor Profile
              </th>
              {hours.map((h, i) => (
                <th
                  key={h}
                  className="text-[10px] text-ink-faint font-black tnum py-2.5 px-1 text-center border-l border-line/40"
                  title={labels[i]}
                >
                  {h % 3 === 0 ? String(h).padStart(2, "0") : ""}
                </th>
              ))}
              <th className="text-[10px] uppercase font-black tracking-wider text-ink-faint py-3 px-3.5 text-right border-l border-line/60">
                Safe Hrs
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {data.personas.order.map((key) => {
              const p = data.personas.personas[key];
              return (
                <tr key={key} className="hover:bg-sunken/20 transition-colors">
                  <td className="px-3.5 py-2.5 align-middle">
                    <div className="text-[13px] font-black text-ink leading-tight truncate max-w-60" title={p.notes}>
                      {p.label}
                    </div>
                    <div className="text-[10px] text-ink-faint tnum font-semibold mt-0.5">
                      Threshold {p.limit_c} °C
                      {p.full_capacity_hours.length === 0 && (
                        <span className="ml-1.5 text-flag font-black">
                          · 0 full-capacity hrs
                        </span>
                      )}
                    </div>
                  </td>
                  {p.safe_minutes_by_hour.map((minutes, i) => {
                    const s = swatch(minutes);
                    const isSelected = i === hour;
                    return (
                      <td key={i} className="p-0.5 text-center border-l border-line/40">
                        <button
                          onClick={() => onHour(i)}
                          title={`${labels[i] ?? i} IST — ${minutes} min/hour allowed`}
                          aria-label={`${p.label} at ${labels[i] ?? i}: ${
                            minutes === 0
                              ? "no safe outdoor work"
                              : `${minutes} minutes of work permitted per hour`
                          }`}
                          className={`w-full h-7 rounded text-[10px] font-black tnum transition-all ${
                            isSelected ? "ring-2 ring-accent ring-offset-1 z-10 scale-105" : "hover:opacity-80"
                          }`}
                          style={{ background: s.bg, color: s.ink }}
                        >
                          {minutes === 0 ? "0" : minutes}
                        </button>
                      </td>
                    );
                  })}
                  <td className="px-3.5 py-2.5 text-[14px] tnum font-black text-ink text-right border-l border-line/60">
                    {p.total_safe_hours}h
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-4">
        <span className="text-[10px] uppercase font-black tracking-wider text-ink-faint">
          Work Allowance Swatches:
        </span>
        {[
          { m: 60, l: "60 min (Full)" },
          { m: 45, l: "45 min" },
          { m: 30, l: "30 min" },
          { m: 15, l: "15 min" },
          { m: 0, l: "0 min (Unsafe)" },
        ].map(({ m, l }) => {
          const s = swatch(m);
          return (
            <span
              key={m}
              className="px-2.5 py-0.5 text-[10px] font-black tnum border border-line rounded-lg shadow-2xs"
              style={{ background: s.bg, color: s.ink }}
            >
              {l}
            </span>
          );
        })}
      </div>

      <div className="mt-4 p-3.5 bg-brand-soft/70 border border-brand/30 rounded-xl shadow-2xs">
        <p className="text-[12px] leading-relaxed text-ink font-medium">
          {heavy && (
            <>
              {heavy.label} get{" "}
              <strong className="text-brand font-bold">
                {heavy.full_capacity_hours.length === 0
                  ? "no full-capacity working hours"
                  : `${heavy.full_capacity_hours.length} full-capacity working hour${heavy.full_capacity_hours.length === 1 ? "" : "s"}`}
              </strong>{" "}
              on this day.{" "}
            </>
          )}
          {longestRun > 0 ? (
            <>
              For <strong className="text-brand font-bold">{longestRun} consecutive hour{longestRun === 1 ? "" : "s"}</strong>, nobody in any group can safely work outdoors under ISO 7243 limits.
            </>
          ) : (
            "There is no hour when every group is barred from outdoor work."
          )}
        </p>
      </div>

      <div className="flex flex-wrap gap-2 mt-3">
        <Badge tone="ok">ISO 7243 / ACGIH Occupational Standards</Badge>
        <Badge tone="warn">Vulnerability offsets applied</Badge>
      </div>

      <Note>
        Calculated using citywide environmental metrics. Neighbourhood-specific limits adjust with local microclimates (UHI departure).
      </Note>
    </Panel>
  );
}


