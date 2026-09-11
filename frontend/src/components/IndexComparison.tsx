import type { HeatData } from "../types";
import { Note, Panel } from "./ui";
import { Info } from "./Info";

export function IndexComparison({ data }: { data: HeatData }) {
  const g = data.meta.kill_gate;
  const rows = [
    { label: "Shade air temperature", spread: g.air_temp_spread_c, ratio: 1, tag: "Standard Weather Forecast", desc: "Basic ambient air temp (ignores radiation & humidity)" },
    { label: "Heat stress for outdoor workers (WBGT)", spread: g.wbgt_spread_c, ratio: g.wbgt_damping_ratio, tag: "Work Limit (ISO 7243)", desc: "Occupational heat stress index heavily weighted by humidity" },
    { label: "What the heat feels like (UTCI)", spread: g.utci_spread_c, ratio: g.utci_amplification, tag: "Human Feel (UTCI)", desc: "Comprehensive human thermal model including radiation & wind" },
  ];
  const max = Math.max(...rows.map((r) => r.spread));

  return (
    <Panel
      title="The same city, measured three ways"
      subtitle="How big the gap between neighbourhoods looks depends on which measure you use"
    >
      <div className="space-y-4">
        {rows.map((r) => (
          <div key={r.label} className="bg-surface p-4 rounded-xl border border-line shadow-2xs">
            <div className="flex flex-wrap items-center justify-between text-[12px] gap-2 mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-black text-ink">{r.label}</span>
                <span className="text-[9px] uppercase font-black tracking-wider px-2 py-0.5 rounded bg-sunken text-ink-soft border border-line">
                  {r.tag}
                </span>
              </div>
              <div className="tnum text-ink-soft font-semibold">
                City Disparity Spread:{" "}
                <strong className="text-ink text-[15px] font-black">
                  {r.spread.toFixed(2)} °C
                </strong>
                <span className="ml-2 px-2 py-0.5 rounded-lg bg-accent-soft text-accent text-[11px] font-black border border-accent/20">
                  ×{r.ratio.toFixed(2)} factor
                </span>
              </div>
            </div>

            <div className="h-4 bg-sunken rounded-lg overflow-hidden p-0.5 border border-line/40 mb-1.5">
              <div
                className="h-full rounded-md transition-all duration-500"
                style={{
                  width: `${(r.spread / max) * 100}%`,
                  background:
                    r.ratio > 1.1
                      ? "var(--color-ramp-6)"
                      : r.ratio < 0.7
                        ? "var(--color-ramp-2)"
                        : "var(--color-ramp-4)",
                }}
              />
            </div>
            <p className="text-[11px] text-ink-faint font-medium">{r.desc}</p>
          </div>
        ))}
      </div>

      <div className="mt-4.5 p-3.5 bg-sunken/50 rounded-xl border border-line text-[12px] leading-relaxed text-ink-soft space-y-2 font-medium">
        <p>
          <strong className="text-ink font-bold">Why the indices disagree:</strong> Hot concrete heats the air but contains no moisture, making the hottest neighbourhoods also the driest. <Info term="WBGT" label="WBGT" /> relies heavily on humidity, so temperature elevation and low humidity cancel out, under-stating urban heat variation (×{g.wbgt_damping_ratio.toFixed(2)}). <Info term="UTCI" label="UTCI" /> responds directly to temperature, sun, and wind, revealing full heat disparities across the city (×{g.utci_amplification.toFixed(2)}).
        </p>
      </div>

      <Note>
        Vapour pressure is conserved across zones and relative humidity is recomputed locally per H3 cell.
      </Note>
    </Panel>
  );
}


