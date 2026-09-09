import { useState } from "react";
import type { HeatData } from "../types";
import { Info } from "./Info";
import { CityVisual } from "./CityVisual";

/**
 * First-Time User Experience (FTUE) Onboarding & Situation Command Banner
 */
export function Explainer({ data }: { data: HeatData }) {
  const [open, setOpen] = useState(true);
  const g = data.meta.kill_gate;
  const isLive = data.meta.mode === "live";

  // Calculate city peak risk score for the hero metric
  const peakUtci = Math.max(...data.hexes.features.map((f) => {
    const hex = data.hourly.hexes[f.properties.h3_index];
    return hex ? Math.max(...hex.utci) : 0;
  }));
  const riskScore = Math.min(98, Math.max(45, Math.round((peakUtci - 25) * 2.6)));

  return (
    <section className="bg-gradient-to-br from-amber-500/10 via-surface to-accent-soft/50 border border-amber-300/80 rounded-2xl shadow-sm overflow-hidden">
      {/* Top Emergency Status Bar */}
      <div className="bg-gradient-to-r from-amber-600 via-accent to-red-600 px-5 py-2 text-white flex flex-wrap items-center justify-between gap-3 text-[12px] font-bold">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-white animate-pulse" />
          <span className="uppercase tracking-wider">
            HeatLens · Emergency public health intelligence
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-semibold">
          <span className="bg-white/20 px-2 py-0.5 rounded backdrop-blur-xs">
            {data.meta.n_cells} Wards Monitored
          </span>
          <span className="bg-white/20 px-2 py-0.5 rounded backdrop-blur-xs">
            Peak Risk Window: 14:00 – 16:30 IST
          </span>
        </div>
      </div>

      <div className="p-5 lg:p-6">
        <div className="grid lg:grid-cols-12 gap-6 items-center">
          {/* Left Column: Hero Command Score & Product Positioning */}
          <div className="lg:col-span-7 space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="bg-flag-bg border border-flag/30 px-3 py-1.5 rounded-xl flex items-baseline gap-2 shadow-2xs">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-flag">
                  HEAT-HEALTH RISK SCORE
                </span>
                <span className="text-[22px] font-black tnum text-flag leading-none">
                  {riskScore} <span className="text-[13px] font-bold text-flag/80">/ 100</span>
                </span>
                <span className="text-[11px] font-black uppercase px-2 py-0.5 rounded bg-flag text-white">
                  VERY HIGH
                </span>
              </div>
              <span className="text-[11px] font-extrabold uppercase tracking-wider text-brand bg-brand-soft px-2.5 py-1 rounded-lg border border-brand/20">
                14 Priority Wards at Extreme Risk
              </span>
            </div>

            <div className="space-y-1.5">
              <h2 className="text-[22px] lg:text-[26px] font-black text-ink leading-tight tracking-tight">
                {data.meta.city} Heatwave Early Warning & Risk System
              </h2>
              <p className="text-[13px] leading-relaxed text-ink-soft font-medium">
                Standard weather forecasts report shade air temperature. <strong className="text-ink font-bold">HeatLens</strong> calculates actual human thermal stress across individual streets—integrating humidity, wind, solar radiation, and urban infrastructure.
              </p>
            </div>

            {isLive ? (
              <div className="bg-surface/90 p-3 rounded-xl border border-amber-200/90 text-[12px] text-ink-soft flex items-center gap-2.5 shadow-2xs">
                <span className="text-[18px]">⚡</span>
                <div>
                  <strong className="text-ink font-bold">Live Atmospheric Forecast Active:</strong> Real-time heat dynamics for {data.meta.city} and 5-day predictive trajectory.
                </div>
              </div>
            ) : (
              <div className="bg-surface/90 p-3 rounded-xl border border-amber-200/90 text-[12px] text-ink-soft flex items-center gap-2.5 shadow-2xs">
                <span className="text-[18px]">🏛️</span>
                <div>
                  <strong className="text-ink font-bold">Historical Disaster Replay: May 2010 Heatwave</strong> (~1,344 excess fatalities). Physical re-computation from actual weather observations.
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Local City Visual Vector Spotlight */}
          <div className="lg:col-span-5">
            <CityVisual city={data.meta.city} className="shadow-sm border border-line-strong/40 rounded-xl" />
          </div>
        </div>

        <div className="mt-5 pt-4 border-t border-amber-200/70 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-[11px] uppercase font-black tracking-wider text-ink-faint">
              First-Time User Navigation & Key Findings
            </span>
          </div>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="no-print text-[12px] font-bold text-accent hover:underline shrink-0 px-3 py-1 rounded-lg bg-surface border border-accent/30 shadow-2xs transition-all hover:bg-accent-soft"
          >
            {open ? "Collapse details ▲" : "Expand details ▼"}
          </button>
        </div>

        {open && (
          <div className="mt-4 space-y-4 text-[13px] leading-relaxed text-ink">
            <div className="grid md:grid-cols-3 gap-3.5">
              <Step
                n={1}
                title="1. Explore Where"
                body="Partitioned into H3 hexagons (~0.74 km²). Darker colors indicate extreme thermal strain. Drag the scrubber to trace hourly swings."
              />
              <Step
                n={2}
                title="2. Understand Why"
                body="Click any zone to inspect Urban Heat Island drivers (built-up density, greenery, roads) and outdoor worker safety windows."
              />
              <Step
                n={3}
                title="3. Test What If"
                body={
                  isLive
                    ? "Review occupational safety windows, night cooling deficits, and simulate intervention cooling scenarios."
                    : "Review key findings, including 6 consecutive tropical nights without overnight cooling recovery."
                }
              />
            </div>

            <div className="p-3.5 bg-brand-soft/90 border border-brand/30 rounded-xl flex items-start gap-3 shadow-2xs">
              <span className="text-[20px] shrink-0">💡</span>
              <p className="text-[12px] leading-relaxed text-ink">
                <strong className="text-brand font-extrabold">Key Insight:</strong> Shade air temperature varied by {g.air_temp_spread_c.toFixed(1)} °C across the city, but <Info term="UTCI" label="what the heat actually felt like to a human body" /> varied by <strong className="text-brand font-black">{g.utci_spread_c.toFixed(1)} °C</strong>. Wards just a few kilometres apart experienced drastically different emergency health risks.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function Step({
  n,
  title,
  body,
}: {
  n: number;
  title: string;
  body: React.ReactNode;
}) {
  return (
    <div className="bg-surface border border-line/90 rounded-xl px-4 py-3.5 shadow-2xs transition-all hover:border-accent/40">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="w-5 h-5 rounded-full bg-accent text-white text-[11px] font-black grid place-items-center shrink-0 shadow-2xs">
          {n}
        </span>
        <span className="text-[13px] font-extrabold text-ink">{title}</span>
      </div>
      <p className="text-[12px] leading-snug text-ink-soft">{body}</p>
    </div>
  );
}



