import type { HeatData } from "../types";
import type { Situation } from "../summary";
import { shortDate, weekday } from "../summary";
import { LevelChip, Note, Panel } from "./ui";

/** Day-by-day felt heat for every day the dataset covers. Replaces a card row
 *  that was labelled "3-day forecast" and showed overnight temperatures as the
 *  daytime peak. */
export function DailyOutlook({ data, s }: { data: HeatData; s: Situation }) {
  const isLive = data.meta.mode === "live";
  const days = s.days;
  if (!days.length) return null;

  return (
    <Panel
      title={isLive ? `The next ${days.length} days` : "The 2010 event, day by day"}
      subtitle="Highest city-average feels-like heat each day (09:00 to 18:00), and how far the following night cooled"
    >
      <ol className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
        {days.map((d) => (
          <li
            key={d.date}
            className={`rounded-xl border p-3 ${d.isWorst ? "border-ink bg-surface" : "border-line bg-sunken/40"}`}
          >
            <div className="text-[13px] text-ink-soft">
              {weekday(d.date)} {shortDate(d.date)}
            </div>
            <div className="text-[22px] font-bold text-ink tnum leading-tight mt-0.5">
              {d.maxUtci.toFixed(1)} °C
            </div>
            <div className="text-[12px] text-ink-faint">feels like · air {d.maxAir.toFixed(1)} °C</div>
            <div className="mt-2">
              <LevelChip verdict={d.verdict} />
            </div>
            {d.nightMin !== null && (
              <div className="text-[12px] text-ink-soft mt-2">Night low {d.nightMin.toFixed(1)} °C</div>
            )}
            <div className="mt-1 flex flex-wrap gap-1 text-[11px] font-semibold">
              {d.isWorst && <span className="text-ink">Highest felt heat</span>}
              {d.isFocus && <span className="text-accent">{d.isWorst ? "· " : ""}shown on map</span>}
            </div>
          </li>
        ))}
      </ol>
      <Note>
        City average, so individual neighbourhoods run hotter. The map shows the day marked “shown on map”.
      </Note>
    </Panel>
  );
}
