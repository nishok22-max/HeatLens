import type { Situation } from "../summary";
import { LevelChip, Panel } from "./ui";

/** Hottest neighbourhoods at the peak hour, genuinely sorted. The previous
 *  version listed the first four zones in file order under a "priority" label. */
export function PriorityZones({
  s,
  onSelect,
}: {
  s: Situation;
  onSelect: (h3: string) => void;
}) {
  return (
    <Panel title="Hottest neighbourhoods" subtitle={`Ranked by feels-like heat at ${s.peakLabel}`}>
      <ol className="space-y-2">
        {s.topZones.map((z, i) => (
          <li key={z.h3}>
            <button
              onClick={() => onSelect(z.h3)}
              className="w-full flex items-center justify-between gap-3 p-2.5 rounded-lg border border-line bg-surface hover:bg-sunken text-left transition-colors"
            >
              <span className="flex items-center gap-3 min-w-0">
                <span className="w-6 text-[14px] font-bold text-ink-faint tnum shrink-0">{i + 1}</span>
                <span className="min-w-0">
                  <span className="block text-[14px] font-semibold text-ink truncate">{z.place}</span>
                  <span className="block text-[12px] text-ink-soft tnum">feels like {z.utci.toFixed(1)} °C</span>
                </span>
              </span>
              <LevelChip verdict={z.verdict} />
            </button>
          </li>
        ))}
      </ol>
      <p className="text-[12px] text-ink-faint mt-3">
        Zone names are the nearest place on OpenStreetMap, not official ward boundaries.
      </p>
    </Panel>
  );
}
