import { useState, useEffect, useCallback, useMemo } from "react";
import type { ReactNode } from "react";
import type { DatasetKey } from "./data";
import { DATASETS } from "./data";
import type { HeatData, MetricKey } from "./types";
import { METRICS, METRIC_ORDER } from "./metrics";
import type { ScaleMode } from "./metrics";
import { computeSituation } from "./summary";
import type { ViewKey } from "./components/AppShell";
import { AppShell } from "./components/AppShell";
import { HexMap } from "./components/HexMap";
import { CellDetail } from "./components/CellDetail";
import { ZonePicker } from "./components/ZonePicker";
import { StatusHero } from "./components/StatusHero";
import type { Role } from "./components/StatusHero";
import { PriorityZones } from "./components/PriorityZones";
import { DailyOutlook } from "./components/DailyOutlook";
import { Scenarios } from "./components/Scenarios";
import { AskWhatIf } from "./components/AskWhatIf";
import { ActionList } from "./components/ActionList";
import { SafeWorkGrid } from "./components/SafeWorkGrid";
import { ChatPanel } from "./components/ChatPanel";
import { checkBackendHealth, fetchHeatDataFromAPI } from "./api";

const SCALE_OPTIONS: { key: ScaleMode; label: string }[] = [
  { key: "levels", label: "Heat levels" },
  { key: "contrast", label: "Relative to this hour" },
  { key: "absolute", label: "Fixed range" },
];

export default function App() {
  const [dataset, setDataset] = useState<DatasetKey>("historical");
  const [activeData, setActiveData] = useState<HeatData>(DATASETS.historical.data);

  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [backendLoading, setBackendLoading] = useState<boolean>(false);

  const [view, setView] = useState<ViewKey>("dashboard");
  const [role, setRole] = useState<Role>("commissioner");
  const [metric, setMetric] = useState<MetricKey>("utci");
  const [hour, setHour] = useState(() => computeSituation(DATASETS.historical.data).peakHour);
  const [selected, setSelected] = useState<string | null>(null);
  const [scaleMode, setScaleMode] = useState<ScaleMode>("levels");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadData = useCallback(async (key: DatasetKey) => {
    setBackendLoading(true);
    const status = await checkBackendHealth();
    setBackendConnected(status.connected);

    if (status.connected) {
      const result = await fetchHeatDataFromAPI(key);
      setActiveData(result.data);
      setBackendConnected(result.fromBackend);
    } else {
      setActiveData(DATASETS[key].data);
    }
    setBackendLoading(false);
  }, []);

  useEffect(() => {
    loadData(dataset);
  }, [dataset, loadData]);

  const data = activeData;
  const situation = useMemo(() => computeSituation(data), [data]);
  const labels = data.hourly.meta.labels_ist ?? [];
  const label = labels[hour] ?? `${String(hour).padStart(2, "0")}:00`;

  function switchDataset(key: DatasetKey) {
    setDataset(key);
    // Show the bundled copy at once; the API overlay upgrades it when it answers.
    // Without this, the previous dataset stays on screen while the health probe runs.
    setActiveData(DATASETS[key].data);
    setSelected(null);
    // Open on the hour that matters, not a fixed 14:00.
    setHour(computeSituation(DATASETS[key].data).peakHour);
  }

  /** `fill`: stretch to the parent's height (the single-screen heat-map page)
   *  instead of using a fixed height. */
  const mapBlock = (height: string, fill = false) => (
    <div className={`card overflow-hidden ${fill ? "flex flex-col w-full" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-line">
        <div className="flex flex-wrap gap-1 bg-sunken p-1 rounded-lg no-print" role="group" aria-label="What the map shows">
          {METRIC_ORDER.map((key) => {
            const active = metric === key;
            return (
              <button
                key={key}
                onClick={() => setMetric(key)}
                aria-pressed={active}
                title={METRICS[key].description}
                className={`px-3 py-1.5 rounded-md text-[13px] whitespace-nowrap transition-colors ${
                  active ? "bg-surface text-ink font-semibold shadow-sm" : "text-ink-soft hover:text-ink"
                }`}
              >
                {METRICS[key].plain}
              </button>
            );
          })}
        </div>

        <button
          onClick={() => setShowAdvanced((v) => !v)}
          aria-expanded={showAdvanced}
          className="text-[13px] text-ink-soft hover:text-ink no-print"
        >
          {showAdvanced ? "Hide colour options" : "Colour options"}
        </button>
        {showAdvanced && (
          <div className="basis-full flex flex-wrap items-center gap-2 no-print">
            <span className="text-[13px] text-ink-soft">Colour the map by:</span>
            <div className="flex gap-1 bg-sunken p-1 rounded-lg" role="group" aria-label="Colour scale">
              {SCALE_OPTIONS.map((o) => (
                <button
                  key={o.key}
                  onClick={() => setScaleMode(o.key)}
                  aria-pressed={scaleMode === o.key}
                  className={`px-3 py-1 rounded-md text-[13px] transition-colors ${
                    scaleMode === o.key ? "bg-surface text-ink font-semibold shadow-sm" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={height}>
        <HexMap
          data={data}
          metric={metric}
          hour={hour}
          selected={selected}
          onSelect={setSelected}
          scaleMode={scaleMode}
        />
      </div>

      <div className="flex items-center gap-4 px-4 py-3 border-t border-line">
        <label htmlFor="hour-slider" className="text-[13px] text-ink-soft shrink-0">
          Time of day
        </label>
        <input
          id="hour-slider"
          type="range"
          min={0}
          max={labels.length - 1 || 23}
          value={hour}
          onChange={(e) => setHour(Number(e.target.value))}
          className="flex-1 accent-accent h-2 cursor-pointer"
        />
        <span className="text-[15px] font-semibold text-ink tnum shrink-0 w-16 text-right">{label}</span>
        {hour !== situation.peakHour && (
          <button
            onClick={() => setHour(situation.peakHour)}
            className="text-[13px] text-accent hover:underline shrink-0 no-print"
          >
            Jump to peak
          </button>
        )}
      </div>
    </div>
  );

  const detailCard = (
    <div className="card overflow-hidden">
      <CellDetail data={data} h3={selected} hour={hour} onClose={() => setSelected(null)} />
    </div>
  );

  return (
    <>
      <AppShell
        data={data}
        dataset={dataset}
        onDataset={switchDataset}
        view={view}
        onView={setView}
        hourLabel={label}
        backendConnected={backendConnected}
        backendLoading={backendLoading}
        onRetryBackend={() => loadData(dataset)}
      >
        {view === "dashboard" && (
          <div className="w-full space-y-8">
            {/* The Overview is deliberately short: the situation with its three
                charts, then the day-by-day outlook. Everything else has its
                own page in the sidebar. */}
            <StatusHero data={data} s={situation} role={role} onRole={setRole} onNavigate={setView} />

            <Section title="When it will peak">
              <DailyOutlook data={data} s={situation} />
            </Section>
          </div>
        )}

        {view === "map" && (
          // One screen on desktop: the page takes the viewport height, the map
          // stretches to fill it, and only the zone panel scrolls if it must.
          <div className="flex flex-col gap-3 xl:h-[calc(100vh-190px)] xl:min-h-[640px]">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-[22px] font-bold text-ink tracking-tight">Heat map</h2>
                <p className="text-[13px] text-ink-soft">
                  Click any hexagon, or find a place, to see what it is like there.
                </p>
              </div>
              <div className="w-full sm:w-80">
                <ZonePicker data={data} metric={metric} hour={hour} selected={selected} onSelect={setSelected} />
              </div>
            </div>
            <div className="grid xl:grid-cols-12 gap-4 flex-1 min-h-0">
              {/* The map is limited by height, not width (the city is roughly
                  square), so the zone panel gets the wider share. */}
              <div className="xl:col-span-5 flex min-h-0">
                {mapBlock("h-[420px] xl:h-auto xl:flex-1 xl:min-h-0", true)}
              </div>
              <div className="xl:col-span-7 min-h-0 xl:overflow-y-auto rounded-2xl">
                {selected ? detailCard : <PriorityZones s={situation} onSelect={setSelected} />}
              </div>
            </div>
          </div>
        )}

        {view === "work" && (
          <div className="space-y-5">
            <ViewHeading
              title="Work safety"
              subtitle="How many minutes per hour each kind of worker can safely work outdoors (ISO 7243 and ACGIH limits)."
            />
            <SafeWorkGrid data={data} hour={hour} onHour={setHour} />
            <div className="grid lg:grid-cols-2 gap-5 items-start">
              {mapBlock("h-[380px]")}
              {detailCard}
            </div>
          </div>
        )}

        {view === "scenarios" && (
          <div className="space-y-5">
            <ViewHeading title="What if the city acts?" subtitle="Compare interventions, or ask your own question." />
            <Scenarios insights={data.insights} />
            <AskWhatIf insights={data.insights} backendConnected={backendConnected} dataset={dataset} />
            <ActionList insights={data.insights} />
          </div>
        )}
      </AppShell>

      {/* Phase 5G — chat agent, hides itself when backend is unreachable (D16) */}
      <ChatPanel backendConnected={backendConnected} dataset={dataset} />
    </>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section>
      <div className="mb-3">
        <h2 className="text-[20px] font-bold text-ink tracking-tight">{title}</h2>
        {subtitle && <p className="text-[14px] text-ink-soft">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function ViewHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="border-b border-line pb-3">
      <h2 className="text-[24px] font-bold text-ink tracking-tight">{title}</h2>
      <p className="text-[14px] text-ink-soft">{subtitle}</p>
    </div>
  );
}
