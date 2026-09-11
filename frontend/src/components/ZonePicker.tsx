import { useMemo } from "react";
import type { HeatData, MetricKey } from "../types";
import { METRICS, formatValue } from "../metrics";

/** Compact "find a place" box for the heat-map header. Picking a name selects
 *  that place's hottest zone at the current hour. */
export function ZonePicker({
  data,
  metric,
  hour,
  selected,
  onSelect,
}: {
  data: HeatData;
  metric: MetricKey;
  hour: number;
  selected: string | null;
  onSelect: (h3: string) => void;
}) {
  const def = METRICS[metric];

  const options = useMemo(() => {
    const byName = new Map<string, { h3: string; value: number }>();
    for (const f of data.hexes.features) {
      const name = f.properties.place;
      if (!name) continue;
      const value = data.hourly.hexes[f.properties.h3_index]?.[metric][hour];
      if (!Number.isFinite(value)) continue;
      const current = byName.get(name);
      if (!current || value > current.value) {
        byName.set(name, { h3: f.properties.h3_index, value });
      }
    }
    return [...byName.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [data, metric, hour]);

  if (!options.length) return null;

  const selectedName =
    data.hexes.features.find((f) => f.properties.h3_index === selected)?.properties.place ?? "";

  return (
    <div>
      <label htmlFor="zone-picker" className="block text-[12px] text-ink-soft mb-1">
        Find a neighbourhood ({options.length} named places)
      </label>
      <select
        id="zone-picker"
        value={selectedName}
        onChange={(e) => {
          const hit = options.find((o) => o.name === e.target.value);
          if (hit) onSelect(hit.h3);
        }}
        title="Names are the nearest OpenStreetMap place, not official ward boundaries. Picking a place selects its hottest zone at this hour."
        className="w-full bg-surface border border-line rounded-lg px-3 py-2 text-[14px] text-ink hover:border-accent focus:ring-2 focus:ring-accent/20 focus:border-accent cursor-pointer"
      >
        <option value="">Choose a place…</option>
        {options.map((o) => (
          <option key={o.name} value={o.name}>
            {o.name} · {formatValue(o.value, def)}
          </option>
        ))}
      </select>
    </div>
  );
}
