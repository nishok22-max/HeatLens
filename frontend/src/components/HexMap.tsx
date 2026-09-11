import { useMemo, useRef, useState } from "react";
import type { HeatData, MetricKey } from "../types";
import type { ScaleMode } from "../metrics";
import {
  METRICS,
  RAMP,
  TONE_COLOUR,
  colourInDomain,
  domainFor,
  formatValue,
  paddedDomain,
} from "../metrics";
import { levelBands, verdictFor } from "../plain";
import { placeName } from "../summary";

/**
 * The console map — hand-rolled SVG rather than MapLibre.
 *
 * WHY NOT MAPLIBRE:
 * MapLibre v6 loads its parser in a separate web worker
 * (`assets/maplibre-gl-worker.mjs`). Chromium refuses to construct a worker
 * from a `file://` origin, so the map would render blank exactly when the demo
 * is opened straight from disk — which is the scenario NFR-1 exists to protect.
 *
 * And we do not need what MapLibre is for. There is no basemap (by design, so
 * nothing is fetched), no tiles, no reprojection, and 392 polygons is a trivial
 * amount of geometry. Rendering them directly buys:
 *
 *   - guaranteed offline operation, no worker and no network
 *   - ~1.5 MB less bundle
 *   - vector output that prints correctly
 *   - real keyboard accessibility: each cell is a focusable element
 *
 * Projection is equirectangular with a cos(latitude) correction, which is
 * indistinguishable from anything fancier across a 16 km city.
 */

const VIEW_W = 1000;
const PAD = 8;

export function HexMap({
  data,
  metric,
  hour,
  selected,
  onSelect,
  scaleMode,
}: {
  data: HeatData;
  metric: MetricKey;
  hour: number;
  selected: string | null;
  onSelect: (h3: string | null) => void;
  scaleMode: ScaleMode;
}) {
  const def = METRICS[metric];
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const { cells, viewH } = useMemo(() => {
    const { bbox } = data.meta;
    const latMid = (bbox.min_lat + bbox.max_lat) / 2;
    const kx = Math.cos((latMid * Math.PI) / 180);
    const spanLon = (bbox.max_lon - bbox.min_lon) * kx;
    const spanLat = bbox.max_lat - bbox.min_lat;
    const scale = (VIEW_W - PAD * 2) / spanLon;
    const height = spanLat * scale + PAD * 2;

    const project = (lon: number, lat: number): [number, number] => [
      PAD + (lon - bbox.min_lon) * kx * scale,
      // SVG y grows downward; latitude grows upward.
      height - PAD - (lat - bbox.min_lat) * scale,
    ];

    const list = data.hexes.features.map((f) => {
      const points = f.geometry.coordinates[0]
        .map(([lon, lat]) => project(lon, lat).map((n) => n.toFixed(1)).join(","))
        .join(" ");
      return { props: f.properties, points };
    });

    return { cells: list, viewH: height };
  }, [data]);

  // Absolute = the metric's fixed all-day domain. Contrast = rescaled to the
  // values actually present at this hour, which is the only way the intra-city
  // pattern is visible at the peak of the event.
  const domain = useMemo<[number, number]>(() => {
    if (scaleMode !== "contrast") return domainFor(metric, data.meta.domains);
    const values = data.hexes.features
      .map((f) => data.hourly.hexes[f.properties.h3_index]?.[metric][hour])
    if (!values.length) return domainFor(metric, data.meta.domains);
    return paddedDomain(Math.min(...values), Math.max(...values));
  }, [data, metric, hour, scaleMode]);

  const viewBox = `${pan.x} ${pan.y} ${VIEW_W / zoom} ${viewH / zoom}`;
  const active = hovered ?? selected;
  const activeSeries = active ? data.hourly.hexes[active] : null;
  const activeProps = active
    ? data.hexes.features.find((f) => f.properties.h3_index === active)?.properties
    : undefined;

  function clampPan(x: number, y: number) {
    const maxX = VIEW_W - VIEW_W / zoom;
    const maxY = viewH - viewH / zoom;
    return { x: Math.min(Math.max(0, x), maxX), y: Math.min(Math.max(0, y), maxY) };
  }

  return (
    <div className="relative h-full w-full bg-sunken overflow-hidden">
      <svg
        viewBox={viewBox}
        className="h-full w-full touch-none"
        style={{ cursor: drag.current ? "grabbing" : "default" }}
        role="img"
        aria-label={`${def.label} across ${data.meta.city}, ${data.meta.n_cells} zones`}
        onMouseDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
        }}
        onMouseMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const perPx = VIEW_W / zoom / rect.width;
          setPan(
            clampPan(d.px - (e.clientX - d.x) * perPx, d.py - (e.clientY - d.y) * perPx),
          );
        }}
        onMouseUp={() => {
          drag.current = null;
        }}
        onMouseLeave={() => {
          drag.current = null;
          setHovered(null);
        }}
      >
        {cells.map(({ props, points }) => {
          const series = data.hourly.hexes[props.h3_index];
          const value = series ? series[metric][hour] : NaN;
          const isSelected = props.h3_index === selected;
          const level = verdictFor(metric, value);
          return (
            <polygon
              key={props.h3_index}
              points={points}
              fill={
                scaleMode === "levels"
                  ? Number.isFinite(value) ? TONE_COLOUR[level.tone].bg : "#cccccc"
                  : colourInDomain(value, domain)
              }
              stroke={isSelected ? "#101010" : "#ffffff"}
              strokeWidth={isSelected ? 3 : 0.5}
              strokeOpacity={isSelected ? 1 : 0.55}
              tabIndex={0}
              role="button"
              aria-label={`${placeName(props)}: ${level.label}, ${def.plain} ${formatValue(value, def)}`}
              style={{ cursor: "pointer", outline: "none" }}
              onClick={() => onSelect(props.h3_index)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(props.h3_index);
                }
              }}
              onMouseEnter={() => setHovered(props.h3_index)}
            />
          );
        })}

        {/* Geographic anchors so the map reads as a place without a basemap. */}
        {cells
          .filter((c) => c.props.water > 0.15)
          .map((c) => (
            <polygon
              key={`w-${c.props.h3_index}`}
              points={c.points}
              fill="none"
              stroke="#2b6ca3"
              strokeWidth={1.8}
              strokeOpacity={0.9}
              pointerEvents="none"
            />
          ))}
        {cells
          .filter((c) => c.props.green > 0.12)
          .map((c) => (
            <polygon
              key={`g-${c.props.h3_index}`}
              points={c.points}
              fill="none"
              stroke="#3f7d43"
              strokeWidth={1.5}
              strokeOpacity={0.85}
              pointerEvents="none"
            />
          ))}
      </svg>

      {/* Hover readout overlay */}
      {active && activeSeries && (
        <div className="absolute top-3 left-3 bg-surface/95 backdrop-blur-md border border-line-strong/60 rounded-xl px-3.5 py-2 pointer-events-none shadow-md">
          <div className="text-[13px] font-semibold text-ink leading-tight">
            {activeProps ? placeName(activeProps) : "Unnamed zone"}
          </div>
          <div className="text-[18px] font-bold tnum text-ink leading-tight mt-0.5">
            {verdictFor(metric, activeSeries[metric][hour]).label}{" "}
            <span className="text-[13px] font-medium text-ink-soft">
              · {formatValue(activeSeries[metric][hour], def)}
            </span>
          </div>
        </div>
      )}

      {/* Floating Zoom Controls */}
      <div className="absolute top-3 right-3 flex flex-col gap-1.5 no-print">
        {[
          { label: "+", title: "Zoom in", act: () => setZoom((z) => Math.min(6, z * 1.5)) },
          { label: "−", title: "Zoom out", act: () => setZoom((z) => Math.max(1, z / 1.5)) },
          {
            label: "⤢",
            title: "Reset view",
            act: () => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            },
          },
        ].map((b) => (
          <button
            key={b.label}
            onClick={b.act}
            title={b.title}
            className="w-8 h-8 bg-surface border border-line rounded-lg text-ink font-bold hover:bg-sunken hover:border-line-strong text-[14px] leading-none shadow-2xs transition-all grid place-items-center"
            aria-label={b.title}
          >
            {b.label}
          </button>
        ))}
      </div>

      <Legend metric={metric} domain={domain} scaleMode={scaleMode} />
    </div>
  );
}

function Legend({
  metric,
  domain,
  scaleMode,
}: {
  metric: MetricKey;
  domain: [number, number];
  scaleMode: ScaleMode;
}) {
  const def = METRICS[metric];
  const [lo, hi] = domain;
  const modeLabel =
    scaleMode === "levels"
      ? "Fixed heat levels"
      : scaleMode === "contrast"
        ? "Relative to this hour: red = hottest now, not necessarily dangerous"
        : "Fixed range across the day";
  return (
    <div className="absolute bottom-3 left-3 bg-surface/95 backdrop-blur-md border border-line-strong/60 rounded-xl px-3.5 py-2.5 shadow-md max-w-[16rem]">
      <div className="text-[12px] font-semibold text-ink">{def.plain}</div>
      <div
        className={`text-[11px] leading-snug mb-2 ${scaleMode === "contrast" ? "text-flag font-semibold" : "text-ink-faint"}`}
      >
        {modeLabel}
      </div>
      {scaleMode === "levels" ? (
        <ul className="space-y-1">
          {levelBands(metric)
            .slice()
            .reverse()
            .map((b) => (
              <li key={b.verdict.label} className="flex items-center gap-2 text-[12px] text-ink">
                <span
                  className="inline-block w-4 h-3 rounded-sm border border-line/60"
                  style={{ background: TONE_COLOUR[b.verdict.tone].bg }}
                  aria-hidden
                />
                <span className="flex-1">{b.verdict.label}</span>
                <span className="tnum text-ink-faint">
                  {Number.isFinite(b.from) ? `≥ ${formatValue(b.from, def)}` : ""}
                </span>
              </li>
            ))}
        </ul>
      ) : (
        <>
          <div className="flex h-3 w-56 overflow-hidden rounded-md border border-line/80">
            {RAMP.map((c) => (
              <div key={c} className="flex-1" style={{ background: c }} />
            ))}
          </div>
          <div className="flex justify-between w-56 mt-1 text-[11px] tnum text-ink">
            <span>{formatValue(lo, def)}</span>
            <span>{formatValue(hi, def)}</span>
          </div>
        </>
      )}
      <div className="mt-2 pt-1.5 border-t border-line/60 flex gap-4 text-[11px] text-ink-faint">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-1 rounded-full bg-[#2b6ca3]" /> Water
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-1 rounded-full bg-[#3f7d43]" /> Parks and greenery
        </span>
      </div>
    </div>
  );
}


/** Fixed domains, deliberately not derived from the visible hour: a rescaling
 *  legend would hide the diurnal swing the scrubber exists to show. */
export const LEGEND_IS_FIXED_DOMAIN = true;
