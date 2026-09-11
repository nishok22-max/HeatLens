import type { HeatData } from "../types";
import type { ViewKey } from "./AppShell";
import { Panel } from "./ui";

type Tier = "measured" | "predicted" | "estimated" | "not_calibrated";

const TIERS: Record<Tier, { title: string; body: string; dot: string }> = {
  measured: {
    title: "Measured, computed or published",
    body:
      "Taken from real observations, international standards, or calculated " +
      "from published equations and checked against a second implementation.",
    dot: "var(--color-ok)",
  },
  predicted: {
    title: "Forecast",
    body: "A prediction for the days ahead. It changes every time we refresh.",
    dot: "var(--color-accent)",
  },
  estimated: {
    title: "Estimated",
    body: "Filled with a stated assumption where local data does not exist yet.",
    dot: "var(--color-gold)",
  },
  not_calibrated: {
    title: "Not yet calibrated",
    body: "Shows which areas are worse than others, not how many people will fall ill.",
    dot: "var(--color-flag)",
  },
};

function tierOf(status: string): Tier {
  const s = status.toLowerCase();
  if (s.includes("not calibrated")) return "not_calibrated";
  if (s.startsWith("predicted")) return "predicted";
  if (s.startsWith("measured") || s.startsWith("published") || s.startsWith("computed"))
    return "measured";
  return "estimated";
}

/** The provenance table, reduced to a few plain answers. Built from
 *  meta.provenance, so it changes when the data does. Empty tiers are dropped
 *  below, so the hindcast shows three and the live forecast shows four. */
export function TrustCard({ data, onNavigate }: { data: HeatData; onNavigate: (v: ViewKey) => void }) {
  const groups: Record<Tier, string[]> = {
    measured: [],
    predicted: [],
    estimated: [],
    not_calibrated: [],
  };
  for (const p of data.meta.provenance) groups[tierOf(p.status)].push(p.plain ?? p.layer);

  return (
    <Panel title="How much to trust this" subtitle="Every layer of data is labelled with where it comes from">
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
        {(Object.keys(TIERS) as Tier[])
          .filter((t) => groups[t].length)
          .map((t) => (
            <div key={t} className="rounded-xl border border-line p-4">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: TIERS[t].dot }} aria-hidden />
                <h3 className="text-[15px] font-semibold text-ink">{TIERS[t].title}</h3>
              </div>
              <p className="text-[13px] text-ink-soft mt-1">{TIERS[t].body}</p>
              <ul className="mt-2 text-[14px] text-ink list-disc pl-5 space-y-0.5">
                {groups[t].map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </div>
          ))}
      </div>
      <button onClick={() => onNavigate("data")} className="mt-4 text-[14px] font-semibold text-accent hover:underline no-print">
        Sources, resolution and known limits →
      </button>
    </Panel>
  );
}
