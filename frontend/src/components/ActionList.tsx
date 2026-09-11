import type { Insights } from "../types";
import { Note, Panel } from "./ui";

const IMPACT = {
  high: { label: "High Impact", cls: "bg-flag-bg text-flag border-flag/30 font-black" },
  medium: { label: "Medium Impact", cls: "bg-exercise-bg text-exercise border-exercise/30 font-black" },
  low: { label: "Low Impact", cls: "bg-sunken text-ink-soft border-line-strong/40 font-extrabold" },
} as const;

const ICONS = ["⏱️", "💧", "🛡️", "🌙", "📋"];

export function ActionList({ insights }: { insights: Insights }) {
  return (
    <Panel
      title="Recommended actions"
      subtitle="Worked out from safety thresholds, ranked by impact"
    >
      <ul className="space-y-3.5">
        {insights.actions.map((a, i) => {
          const impact = IMPACT[a.impact as keyof typeof IMPACT] ?? IMPACT.low;
          return (
            <li
              key={a.title}
              className="flex items-start gap-3.5 bg-surface border border-line/90 p-4 rounded-2xl shadow-2xs hover:border-accent/40 transition-all"
            >
              <span
                className="w-10 h-10 rounded-xl bg-accent-soft text-accent grid place-items-center text-[18px] shrink-0 border border-accent/20 shadow-2xs font-extrabold"
                aria-hidden
              >
                {ICONS[i % ICONS.length]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-[9px] uppercase font-black tracking-wider text-accent">
                      WHAT SHOULD BE DONE
                    </span>
                    <h3 className="text-[14px] font-black text-ink leading-tight">
                      {a.title}
                    </h3>
                  </div>
                  <span
                    className={`text-[9px] uppercase tracking-wider border rounded-md px-2 py-0.5 shrink-0 ${impact.cls}`}
                  >
                    {impact.label}
                  </span>
                </div>
                
                <div className="mt-1.5">
                  <span className="text-[9px] uppercase font-black tracking-wider text-ink-faint">
                    WHY IT IS RECOMMENDED
                  </span>
                  <p className="text-[12px] text-ink-soft font-medium leading-snug">
                    {a.detail}
                  </p>
                </div>

                <div className="mt-2.5 text-[10px] text-accent bg-accent-soft/70 px-2.5 py-1 rounded-lg border border-accent/20 font-mono font-semibold">
                  Evidence basis: {a.evidence}
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      <Note>
        Rule-based operational guidance calculated from threshold limits, not unvalidated text generation.
      </Note>
    </Panel>
  );
}


