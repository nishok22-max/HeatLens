import type { Insights } from "../types";
import { Note, Panel } from "./ui";

/**
 * What-If Intervention Simulator.
 */
export function Scenarios({ insights }: { insights: Insights }) {
  const best = insights.scenarios.reduce((a, b) => (score(b) > score(a) ? b : a));

  return (
    <Panel
      title="Intervention options"
      subtitle="Each option re-run through the heat model and compared with doing nothing"
    >
      <div className="grid md:grid-cols-3 gap-4">
        {insights.scenarios.map((s) => {
          const isWork = typeof s.reduction_pct === "number";
          const isBest = s.key === best.key;
          return (
            <div
              key={s.key}
              className={`rounded-2xl border p-4.5 transition-all flex flex-col justify-between ${
                isBest
                  ? "border-ok bg-gradient-to-b from-ok-bg/70 via-surface to-surface shadow-sm ring-1 ring-ok/30"
                  : "border-line bg-surface hover:border-line-strong shadow-2xs"
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-[10px] font-black uppercase tracking-wider text-accent bg-accent-soft px-2 py-0.5 rounded-md border border-accent/20">
                    Intervention Option
                  </span>
                  {isBest && (
                    <span className="text-[9px] uppercase font-black tracking-wider text-ok bg-ok-bg border border-ok/40 rounded-md px-2 py-0.5 shrink-0 shadow-2xs">
                      ★ Best ROI Strategy
                    </span>
                  )}
                </div>

                <h3 className="text-[15px] font-black text-ink leading-tight">
                  {s.label}
                </h3>
                <p className="text-[12px] text-ink-soft mt-1.5 leading-relaxed font-medium">
                  {s.detail}
                </p>

                {/* Baseline -> Action -> Modelled Estimate Flow */}
                <div className="mt-4 p-3 bg-sunken/40 rounded-xl border border-line/70 space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-bold">
                    <span className="text-ink-faint uppercase text-[9px] tracking-wider">Baseline Risk</span>
                    <span className="text-ink font-extrabold tnum">
                      {isWork ? `${s.unsafe_before}h unsafe` : `${s.utci_before} °C felt`}
                    </span>
                  </div>

                  <div className="flex items-center justify-center text-[12px] text-accent font-black">
                    ↓ [ ACTION APPLIED ] ↓
                  </div>

                  <div className="flex items-baseline justify-between gap-2 pt-1 border-t border-line/60">
                    <div>
                      <span className="block text-[9px] uppercase font-black tracking-wider text-ok">
                        Modelled Scenario Estimate
                      </span>
                      <span className="text-[11px] font-bold text-ink-soft tnum">
                        {isWork ? `${s.unsafe_after}h unsafe` : `${s.utci_after} °C felt`}
                      </span>
                    </div>
                    
                    <div className="text-right">
                      {isWork ? (
                        <span className="text-[24px] font-black text-ok tnum leading-none tracking-tight">
                          −{s.reduction_pct}%
                        </span>
                      ) : (
                        <span className="text-[24px] font-black text-ok tnum leading-none tracking-tight">
                          {s.delta_c} °C
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-line/70">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="uppercase font-black tracking-wider text-ink-faint text-[9px]">
                    Implementation Cost & Feasibility
                  </span>
                  <span className="font-extrabold text-ink bg-sunken px-2 py-0.5 rounded">{s.cost}</span>
                </div>
                <p className="text-[10px] leading-relaxed text-ink-faint mt-1 font-mono">
                  Standard basis: {s.basis}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {insights.omitted?.length > 0 && (
        <div className="mt-5 pt-4 border-t border-line">
          <h4 className="text-[11px] uppercase font-black tracking-wider text-ink-faint mb-2">
            Interventions Omitted from Physical Model Scope
          </h4>
          <div className="grid sm:grid-cols-2 gap-2.5">
            {insights.omitted.map((o) => (
              <div key={o.item} className="text-[12px] leading-relaxed bg-sunken/40 p-3 rounded-xl border border-line/60">
                <span className="text-ink font-extrabold block">{o.item}</span>
                <span className="text-ink-soft font-medium">{o.why}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Note>
        Every scenario outcome is verified by physical microclimate model parameters. Unvalidated interventions are omitted rather than guessed.
      </Note>
    </Panel>
  );
}

function score(s: Insights["scenarios"][number]): number {
  const cost = /no cost/i.test(s.cost) ? 1 : /low/i.test(s.cost) ? 2 : 5;
  const benefit =
    typeof s.reduction_pct === "number"
      ? s.reduction_pct / 10
      : Math.abs(s.delta_c ?? 0);
  return benefit / cost;
}

