import type { HeatData } from "../types";
import { useState } from "react";
import { Badge, Panel, statusTone } from "./ui";

export function ProvenancePanel({ data }: { data: HeatData }) {
  const [showTechnical, setShowTechnical] = useState(false);
  const flagged = data.meta.provenance.filter(
    (p) => statusTone(p.status) !== "ok",
  ).length;

  return (
    <Panel
      title="Data sources and known limits"
      subtitle="Every data layer, where it comes from, and whether it is measured or assumed"
      right={
        <div className="text-right bg-flag-bg border border-flag/30 px-3.5 py-1.5 rounded-xl shadow-2xs">
          <div className="text-[22px] font-black tnum leading-none text-flag">
            {flagged} / {data.meta.provenance.length}
          </div>
          <div className="text-[10px] uppercase font-black tracking-wider text-flag/90 mt-0.5">
            layers using proxy data
          </div>
        </div>
      }
    >
      <div className="overflow-x-auto rounded-xl border border-line shadow-2xs">
        <table className="w-full text-[12px] border-collapse bg-surface">
          <thead>
            <tr className="bg-sunken/60 text-[10px] uppercase font-black tracking-wider text-ink-faint border-b border-line">
              <th className="text-left py-3 px-3.5">Data Layer</th>
              <th className="text-left py-3 px-3.5">Primary Source</th>
              <th className="text-left py-3 px-3.5">Spatial / Temporal Resolution</th>
              <th className="text-left py-3 px-3.5">Verification Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {data.meta.provenance.map((p) => {
              const tone = statusTone(p.status);
              return (
                <tr key={p.layer} className="hover:bg-sunken/20 transition-colors align-top">
                  <td className="py-2.5 px-3.5">
                    <div className="text-ink font-extrabold">{p.plain ?? p.layer}</div>
                    <div className="text-[10px] font-mono text-ink-faint font-semibold">
                      {p.layer}
                    </div>
                  </td>
                  <td className="py-2.5 px-3.5 text-ink-soft font-semibold">{p.source}</td>
                  <td className="py-2.5 px-3.5 text-ink-faint tnum font-semibold whitespace-nowrap">
                    {p.resolution}
                  </td>
                  <td className="py-2.5 px-3.5">
                    <Badge tone={tone}>{plainStatus(p.status)}</Badge>
                    <div className="text-[10px] text-ink-faint mt-1 max-w-56 font-mono leading-tight">
                      {p.status}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-5 pt-4 border-t border-line">
        <div className="flex items-center justify-between gap-3 mb-2.5">
          <h3 className="text-[11px] uppercase font-black tracking-wider text-ink-faint">
            Model Limitations & Known Physical Caveats
          </h3>
          <button
            onClick={() => setShowTechnical((v) => !v)}
            aria-expanded={showTechnical}
            className="no-print text-[12px] font-extrabold text-accent hover:underline shrink-0"
          >
            {showTechnical ? "▲ Hide Technical Details" : "▼ Show Technical Details"}
          </button>
        </div>
        <div className="grid sm:grid-cols-2 gap-2.5">
          {data.meta.caveats.map((c) => (
            <div key={c.technical} className="p-3.5 bg-sunken/40 border border-line/60 rounded-xl text-[12px]">
              <div className="flex items-start gap-2">
                <span className="text-flag font-black text-[15px] shrink-0">⚠️</span>
                <div>
                  <span className="text-ink font-bold block leading-snug">{c.plain}</span>
                  {showTechnical && (
                    <span className="block text-[11px] text-ink-faint mt-1.5 font-mono bg-surface p-2 rounded-lg border border-line">
                      {c.technical}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 pt-4 border-t border-line bg-sunken/30 p-4 rounded-xl border border-line/60 grid grid-cols-2 gap-x-6 gap-y-2 text-[12px]">
        <div className="col-span-2 text-[11px] uppercase font-black tracking-wider text-ink-faint mb-1">
          Exposure-Response Function Calibration Parameters
        </div>
        <span className="text-ink-soft font-semibold">Target Metric & MMT Baseline:</span>
        <span className="text-ink font-black tnum text-right">
          {data.meta.exposure_response.metric.toUpperCase()} · MMT = {data.meta.exposure_response.mmt_c} °C
        </span>
        <span className="text-ink-soft font-semibold">Slope Coefficient (Beta 95% CI):</span>
        <span className="text-ink font-black tnum text-right">
          {data.meta.exposure_response.beta} ({data.meta.exposure_response.beta_ci.join(" – ")})
        </span>
        <span className="text-ink-soft font-semibold">Local Hospital Calibration:</span>
        <span className="text-right">
          <Badge tone={data.meta.exposure_response.is_calibrated ? "ok" : "flag"}>
            {data.meta.exposure_response.is_calibrated ? "Calibrated against local data" : "Uncalibrated placeholder"}
          </Badge>
        </span>
      </div>
    </Panel>
  );
}

function plainStatus(status: string): string {
  const s = status.toLowerCase();
  if (s.startsWith("measured")) return "Measured";
  if (s.startsWith("published")) return "Published standard";
  if (s.includes("not calibrated")) return "Not checked locally";
  if (s.includes("not fitted")) return "Stand-in proxy";
  if (s.includes("assumed")) return "Assumed parameter";
  return status;
}

