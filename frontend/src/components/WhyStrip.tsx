import type { HeatData } from "../types";
import type { DatasetKey } from "../data";
import type { ViewKey } from "./AppShell";

/**
 * Three findings, one sentence each, computed from the kill-gate numbers.
 * Kept out of the hero on purpose: the hero answers "what now", this strip
 * answers "why believe it".
 */
export function WhyStrip({
  data,
  onNavigate,
  onDataset,
}: {
  data: HeatData;
  onNavigate: (v: ViewKey) => void;
  onDataset: (k: DatasetKey) => void;
}) {
  const g = data.meta.kill_gate;
  const isLive = data.meta.mode === "live";

  const cards = [
    {
      title: `${g.utci_spread_c.toFixed(1)} °C apart, same city, same hour`,
      body: `Air temperature differs by ${g.air_temp_spread_c.toFixed(1)} °C across neighbourhoods, but the heat people feel differs by ${g.utci_spread_c.toFixed(1)} °C. A single city-wide forecast hides this.`,
      cta: "See the map",
      act: () => onNavigate("map"),
    },
    {
      title: "One heat index on its own misleads",
      body: `Between neighbourhoods, the worker heat index (WBGT) shows only ${Math.round(g.wbgt_damping_ratio * 100)}% of the air-temperature difference, while felt heat (UTCI) shows ${g.utci_amplification.toFixed(2)}×. HeatLens computes both, and says which one each view uses.`,
      cta: "Compare the indices",
      act: () => onNavigate("findings"),
    },
    isLive
      ? {
          title: "Tested on a real disaster",
          body: "Replay 21 May 2010: the Ahmedabad heatwave linked to an estimated 1,300+ excess deaths, which led to India's first city Heat Action Plan.",
          cta: "Replay May 2010",
          act: () => onDataset("historical"),
        }
      : {
          title: "The same system, looking ahead",
          body: "The pipeline that rebuilt 2010 also runs on today's weather forecast, refreshed automatically, for every neighbourhood.",
          cta: "Open the live forecast",
          act: () => onDataset("live"),
        },
  ];

  return (
    <section aria-label="Why HeatLens" className="grid md:grid-cols-3 gap-3">
      {cards.map((c) => (
        <div key={c.title} className="card p-5 flex flex-col">
          <h3 className="text-[16px] font-bold text-ink leading-snug">{c.title}</h3>
          <p className="text-[14px] text-ink-soft leading-relaxed mt-1.5 flex-1">{c.body}</p>
          <button onClick={c.act} className="mt-3 self-start text-[14px] font-semibold text-accent hover:underline no-print">
            {c.cta} →
          </button>
        </div>
      ))}
    </section>
  );
}
