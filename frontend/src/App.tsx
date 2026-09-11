import { useState, useEffect, useCallback } from "react";
import type { DatasetKey } from "./data";
import { DATASETS } from "./data";
import type { HeatData, MetricKey } from "./types";
import { METRICS, METRIC_ORDER } from "./metrics";
import type { ScaleMode } from "./metrics";
import type { ViewKey } from "./components/AppShell";
import { AppShell } from "./components/AppShell";
import { HexMap } from "./components/HexMap";
import { CellDetail } from "./components/CellDetail";
import { ZonePicker } from "./components/ZonePicker";
import { KpiRow } from "./components/KpiRow";
import { Drivers } from "./components/Drivers";
import { Scenarios } from "./components/Scenarios";
import { AskWhatIf } from "./components/AskWhatIf";
import { ActionList } from "./components/ActionList";
import { IndexComparison } from "./components/IndexComparison";
import { NightRecovery } from "./components/NightRecovery";
import { SafeWorkGrid } from "./components/SafeWorkGrid";
import { AdvisoryPanel } from "./components/AdvisoryPanel";
import { ProvenancePanel } from "./components/ProvenancePanel";
import { Explainer } from "./components/Explainer";
import { Panel } from "./components/ui";
import { ChatPanel } from "./components/ChatPanel";
import { checkBackendHealth, fetchHeatDataFromAPI } from "./api";

export default function App() {
  const [dataset, setDataset] = useState<DatasetKey>("historical");
  const [activeData, setActiveData] = useState<HeatData>(DATASETS.historical.data);

  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [backendLoading, setBackendLoading] = useState<boolean>(false);

  const [view, setView] = useState<ViewKey>("dashboard");
  const [metric, setMetric] = useState<MetricKey>("utci");
  const [hour, setHour] = useState(14);
  const [selected, setSelected] = useState<string | null>(null);
  const [scaleMode, setScaleMode] = useState<ScaleMode>("contrast");

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
  const labels = data.hourly.meta.labels_ist ?? [];
  const label = labels[hour] ?? `${String(hour).padStart(2, "0")}:00`;

  function switchDataset(key: DatasetKey) {
    setDataset(key);
    setSelected(null);
    setHour((h: number) =>
      Math.min(h, DATASETS[key].data.hourly.meta.hours_ist.length - 1),
    );
  }

  const mapBlock = (height: string) => (
    <div className="card overflow-hidden border border-line shadow-sm bg-surface">
      {/* Map Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-surface border-b border-line">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-black uppercase tracking-wider text-ink-faint hidden sm:inline">
            Heat Metric:
          </span>
          <div className="flex flex-wrap gap-1 bg-sunken p-1 rounded-xl no-print border border-line-strong/30">
            {METRIC_ORDER.map((key) => {
              const active = metric === key;
              return (
                <button
                  key={key}
                  onClick={() => setMetric(key)}
                  aria-pressed={active}
                  title={METRICS[key].label}
                  className={`px-3 py-1 rounded-lg text-[12px] font-extrabold whitespace-nowrap transition-all ${
                    active
                      ? "bg-accent text-white shadow-xs"
                      : "text-ink-soft hover:text-ink hover:bg-surface/70 font-semibold"
                  }`}
                >
                  {METRICS[key].plain}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-black uppercase tracking-wider text-ink-faint hidden sm:inline">
            Contrast Scale:
          </span>
          <div className="flex gap-1 bg-sunken p-1 rounded-xl no-print border border-line-strong/30">
            {(["contrast", "absolute"] as ScaleMode[]).map((m) => {
              const active = scaleMode === m;
              return (
                <button
                  key={m}
                  onClick={() => setScaleMode(m)}
                  aria-pressed={active}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-extrabold capitalize transition-all ${
                    active
                      ? "bg-surface text-ink shadow-xs border border-line/60"
                      : "text-ink-soft hover:text-ink font-semibold"
                  }`}
                >
                  {m}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Hex Map SVG Viewport */}
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

      {/* Hour Scrubber Bar */}
      <div className="flex items-center gap-4 px-4 py-3 bg-surface border-t border-line">
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[16px]">🕒</span>
          <span className="text-[11px] font-black uppercase tracking-wider text-ink-faint">
            Hour of day (IST)
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={labels.length - 1 || 23}
          value={hour}
          onChange={(e) => setHour(Number(e.target.value))}
          className="flex-1 accent-accent h-2.5 bg-sunken rounded-lg cursor-pointer"
          aria-label="Hour of day slider (IST)"
        />
        <div className="px-3.5 py-1 bg-accent-soft text-accent border border-accent/25 rounded-xl text-center shrink-0 shadow-2xs">
          <span className="text-[14px] font-black tnum leading-none">{label}</span>
        </div>
      </div>
    </div>
  );

  const detailCard = (
    <div className="card overflow-hidden shadow-sm">
      <CellDetail
        data={data}
        h3={selected}
        hour={hour}
        onClose={() => setSelected(null)}
      />
    </div>
  );

  const finder = (
    <Panel title="FIND YOUR NEIGHBOURHOOD" subtitle="Jump directly to any ward zone by landmark or area name">
      <ZonePicker
        data={data}
        metric={metric}
        hour={hour}
        selected={selected}
        onSelect={setSelected}
      />
    </Panel>
  );

  return (
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
        <div className="w-full max-w-none space-y-7">
          {/* STAGE 1 — SITUATION */}
          <div>
            <StageHeading
              stage="STAGE 1 — SITUATION"
              title="What is happening right now?"
              subtitle="Citywide emergency status, peak heat threat, and priority ward counts"
            />
            <div className="mt-3 space-y-5">
              <Explainer data={data} />
              <KpiRow data={data} />
            </div>
          </div>

          {/* STAGE 2 — WHY */}
          <div>
            <StageHeading
              stage="STAGE 2 — WHY"
              title="Why is the human risk elevated?"
              subtitle="Physiological heat equation: Atmosphere vs Human Thermal Physiology"
            />
            
            <div className="mt-3 card p-5 bg-gradient-to-r from-amber-500/10 via-surface to-teal-500/10 border border-amber-300/80 rounded-2xl shadow-2xs">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-4 border-b border-amber-200/60 pb-2.5">
                <div>
                  <span className="text-[11px] font-black uppercase tracking-wider text-brand">
                    WEATHER → HUMAN THERMAL STRESS PHYSIOLOGY EQUATION
                  </span>
                  <p className="text-[12px] text-ink-soft font-medium mt-0.5">
                    Shade air temperature alone masks heat stroke threats. UTCI & WBGT combine radiation, humidity, and wind.
                  </p>
                </div>
                <span className="text-[11px] font-extrabold text-teal-dark bg-teal-soft px-3 py-1 rounded-lg border border-teal/30">
                  Universal Thermal Climate Index (UTCI)
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-center text-center">
                <div className="p-3 bg-surface border border-line rounded-xl shadow-2xs">
                  <div className="text-[20px]">🌡️</div>
                  <div className="text-[15px] font-black text-ink tnum mt-0.5">
                    {(data.hourly.hexes[data.hexes.features[0]?.properties.h3_index ?? ""]?.air_temp[data.meta.focus.hour_ist] ?? 41).toFixed(1)} °C
                  </div>
                  <div className="text-[10px] text-ink-faint font-extrabold uppercase mt-0.5">Shade Air Temp</div>
                </div>
                <div className="hidden md:block text-[22px] font-black text-amber-600">+</div>
                <div className="p-3 bg-surface border border-line rounded-xl shadow-2xs">
                  <div className="text-[20px]">💧</div>
                  <div className="text-[14px] font-black text-ink tnum mt-0.5">High Humidity</div>
                  <div className="text-[10px] text-ink-faint font-extrabold uppercase mt-0.5">Blocks Evaporative Sweat</div>
                </div>
                <div className="hidden md:block text-[22px] font-black text-amber-600">+</div>
                <div className="p-3 bg-surface border border-line rounded-xl shadow-2xs">
                  <div className="text-[20px]">☀️</div>
                  <div className="text-[14px] font-black text-ink tnum mt-0.5">Solar Radiation</div>
                  <div className="text-[10px] text-ink-faint font-extrabold uppercase mt-0.5">Direct Radiation Absorption</div>
                </div>
              </div>

              <div className="mt-4 pt-3.5 border-t border-amber-200/80 flex flex-wrap items-center justify-between gap-3 bg-brand-soft/90 p-3.5 rounded-xl border border-brand/30 shadow-2xs">
                <div className="flex items-center gap-3">
                  <span className="text-[22px] font-bold text-brand">➔</span>
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-wider text-brand">
                      RESULTING HUMAN THERMAL FEEL
                    </div>
                    <div className="text-[15px] font-black text-ink">
                      Extreme Thermal Stress <span className="text-flag font-black tnum">({(data.hourly.hexes[data.hexes.features[0]?.properties.h3_index ?? ""]?.utci[data.meta.focus.hour_ist] ?? 61.2).toFixed(1)} °C felt)</span>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <span className="text-[11px] font-extrabold text-ink-soft bg-surface px-3 py-1 rounded-lg border border-line">
                    UTCI = Outdoor Thermal Stress
                  </span>
                  <span className="text-[11px] font-extrabold text-ink-soft bg-surface px-3 py-1 rounded-lg border border-line">
                    WBGT = Outdoor Work Limit
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* STAGE 3 — WHERE + WHO */}
          <div>
            <StageHeading
              stage="STAGE 3 — WHERE & WHO"
              title="Where is the risk highest, and who is affected?"
              subtitle="Hyperlocal H3 neighbourhood risk map, Urban Heat Island drivers, and ward details"
            />
            
            <div className="mt-3 card p-5 border border-line rounded-2xl bg-surface space-y-4 shadow-sm">
              <div className="flex items-baseline justify-between border-b border-line/70 pb-2.5">
                <div>
                  <h3 className="text-[16px] font-black text-ink tracking-tight uppercase">
                    HYPERLOCAL HEAT RISK WORKSPACE
                  </h3>
                  <p className="text-[12px] text-ink-soft font-medium">Click any H3 zone on the map to inspect ward details.</p>
                </div>
                <span className="text-[11px] font-mono font-bold text-ink-faint">
                  {data.hexes.features.length} H3 Zones Monitored
                </span>
              </div>
              
              <div className="grid xl:grid-cols-12 gap-5 items-start">
                <div className="xl:col-span-7">
                  {mapBlock("h-[500px] lg:h-[580px] 2xl:h-[650px]")}
                </div>
                <div className="xl:col-span-5 space-y-5">
                  {selected ? detailCard : (
                    <>
                      {finder}
                      <Drivers insights={data.insights} />
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* STAGE 4 — WHEN + WHAT */}
          <div>
            <StageHeading
              stage="STAGE 4 — WHEN & WHAT TO DO"
              title="When will risk peak, and what should authorities do?"
              subtitle="3-day forecast progression, priority ward rankings, and operational recommendations"
            />

            <div className="mt-3 grid lg:grid-cols-12 gap-5 items-start">
              {/* 3-Day Forecast Timeline */}
              <div className="lg:col-span-7 card p-5 border border-line rounded-2xl bg-surface space-y-3 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line/70 pb-2.5">
                  <div>
                    <h3 className="text-[15px] font-black text-ink tracking-tight uppercase">
                      3-DAY FORECAST TIMELINE & PEAK WINDOWS
                    </h3>
                    <p className="text-[11px] text-ink-soft font-medium">Diurnal heat progression and overnight recovery</p>
                  </div>
                  <span className="px-2.5 py-1 rounded-lg bg-flag-bg text-flag text-[10px] font-black border border-flag/30 uppercase">
                    PEAK WINDOW: 14:00 - 16:30 IST
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-3 pt-1">
                  {data.city.night_recovery.slice(0, 3).map((nr: any, idx: number) => (
                    <div key={nr.date} className="p-3.5 bg-sunken/40 rounded-xl border border-line/70 text-center">
                      <div className="text-[10px] font-black uppercase tracking-wider text-ink-faint">
                        {idx === 0 ? "TODAY" : idx === 1 ? "TOMORROW" : `DAY ${idx + 1}`} ({nr.date.split("-").slice(1).join("/")})
                      </div>
                      <div className="text-[20px] font-black text-ink mt-1 tnum">
                        {nr.max_c.toFixed(1)} °C
                      </div>
                      <div className="text-[10px] text-ink-soft font-bold mt-0.5">Overnight Min: {nr.min_c.toFixed(1)} °C</div>
                      <span className={`inline-block mt-2 text-[9px] font-black uppercase px-2 py-0.5 rounded-md ${
                        idx === 0 ? "bg-flag text-white" : "bg-amber-100 text-amber-900 border border-amber-300"
                      }`}>
                        {idx === 0 ? "PEAK RISK DAY" : "ELEVATED THREAT"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Priority Wards Ranking */}
              <div className="lg:col-span-5 card p-5 border border-line rounded-2xl bg-surface space-y-3 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line/70 pb-2.5">
                  <div>
                    <h3 className="text-[15px] font-black text-ink tracking-tight uppercase">
                      TOP PRIORITY WARDS
                    </h3>
                    <p className="text-[11px] text-ink-soft font-medium">Ranked by human thermal stress intensity</p>
                  </div>
                  <button
                    onClick={() => setView("map")}
                    className="text-[11px] font-extrabold text-accent hover:underline"
                  >
                    View Map →
                  </button>
                </div>

                <div className="space-y-2">
                  {data.hexes.features.slice(0, 4).map((f: any, i: number) => {
                    const placeName = f.properties.place || `H3 Zone #${f.properties.h3_index.slice(-4)}`;
                    const riskVal = Math.round(f.properties.risk_focus * 100);
                    const isExtreme = riskVal >= 80;
                    return (
                      <div
                        key={f.properties.h3_index}
                        onClick={() => {
                          setSelected(f.properties.h3_index);
                          setView("map");
                        }}
                        className="flex items-center justify-between p-2.5 bg-sunken/40 hover:bg-sunken rounded-xl border border-line/60 cursor-pointer transition-colors"
                      >
                        <div className="flex items-center gap-2.5">
                          <span className="w-6 h-6 rounded-full bg-navy text-white text-[11px] font-black grid place-items-center shrink-0 shadow-2xs">
                            #{i + 1}
                          </span>
                          <div>
                            <div className="text-[12px] font-extrabold text-ink leading-tight">{placeName}</div>
                            <div className="text-[10px] text-ink-faint font-semibold">High vulnerability density</div>
                          </div>
                        </div>
                        <span className={`text-[11px] font-black px-2.5 py-0.5 rounded-lg ${
                          isExtreme ? "bg-flag-bg text-flag border border-flag/30" : "bg-amber-100 text-amber-900 border border-amber-300"
                        }`}>
                          {isExtreme ? "Extreme" : "Very High"} ({riskVal})
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="mt-5">
              <ActionList insights={data.insights} />
            </div>
          </div>

          {/* STAGE 5 — WHAT IF WE ACT? */}
          <div>
            <StageHeading
              stage="STAGE 5 — WHAT IF WE ACT?"
              title="What happens under different intervention scenarios?"
              subtitle="Modelled scenario simulator comparing baseline risk vs intervention estimates"
            />

            <div className="mt-3 card p-5 border border-amber-300/80 rounded-2xl bg-gradient-to-br from-surface to-gold-soft/30 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-amber-200/80 pb-2.5">
                <div>
                  <h3 className="text-[16px] font-black text-ink tracking-tight uppercase">
                    INTERVENTION SIMULATOR & MODELLED ESTIMATES
                  </h3>
                  <p className="text-[12px] text-ink-soft font-medium">
                    Compare response measures physically re-computed through the thermal model.
                  </p>
                </div>
                <button
                  onClick={() => setView("scenarios")}
                  className="text-[12px] font-extrabold text-accent hover:underline flex items-center gap-1 no-print"
                >
                  <span>Full Simulator</span>
                  <span>→</span>
                </button>
              </div>
              
              <AskWhatIf insights={data.insights} />
              <Scenarios insights={data.insights} />
            </div>
          </div>
        </div>
      )}

      {view === "map" && (
        <div className="space-y-5">
          <div className="border-b border-line pb-2.5">
            <h2 className="text-[20px] font-black text-ink tracking-tight uppercase">HYPERLOCAL RISK MAP WORKSPACE</h2>
            <p className="text-[12px] text-ink-soft font-medium">Explore ward-level human thermal risk across all H3 hexagons.</p>
          </div>
          <div className="grid xl:grid-cols-4 gap-5 items-start">
            <div className="xl:col-span-3">{mapBlock("h-[580px] lg:h-[700px]")}</div>
            <div className="space-y-5">
              {finder}
              {detailCard}
            </div>
          </div>
        </div>
      )}

      {view === "work" && (
        <div className="space-y-5">
          <div className="border-b border-line pb-2.5">
            <h2 className="text-[20px] font-black text-ink tracking-tight uppercase">OCCUPATIONAL WORK SAFETY</h2>
            <p className="text-[12px] text-ink-soft font-medium">Permissible outdoor work windows under ISO 7243 & ACGIH threshold limits.</p>
          </div>
          <SafeWorkGrid data={data} hour={hour} onHour={setHour} />
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            {mapBlock("h-[380px]")}
            {detailCard}
          </div>
        </div>
      )}

      {view === "scenarios" && (
        <div className="space-y-5">
          <div className="border-b border-line pb-2.5">
            <h2 className="text-[20px] font-black text-ink tracking-tight uppercase">INTERVENTION SIMULATION</h2>
            <p className="text-[12px] text-ink-soft font-medium">Compare response measures physically re-evaluated against the baseline heat state.</p>
          </div>
          <AskWhatIf insights={data.insights} />
          <Scenarios insights={data.insights} />
          <ActionList insights={data.insights} />
        </div>
      )}

      {view === "findings" && (
        <div className="space-y-5">
          <div className="border-b border-line pb-2.5">
            <h2 className="text-[20px] font-black text-ink tracking-tight uppercase">ANALYTICAL FINDINGS & DISPARITIES</h2>
            <p className="text-[12px] text-ink-soft font-medium">Understand key diurnal patterns, metric divergence, and night cooling deficits.</p>
          </div>
          <IndexComparison data={data} />
          <NightRecovery data={data} />
          <Drivers insights={data.insights} />
        </div>
      )}

      {view === "advisory" && (
        <div className="space-y-5">
          <div className="border-b border-line pb-2.5">
            <h2 className="text-[20px] font-black text-ink tracking-tight uppercase">PUBLIC ADVISORY WARNING SYSTEM</h2>
            <p className="text-[12px] text-ink-soft font-medium">Multi-lingual CAP 1.2 emergency alert broadcasts for public health authorities.</p>
          </div>
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            <AdvisoryPanel data={data} />
            <ActionList insights={data.insights} />
          </div>
        </div>
      )}

      {view === "data" && (
        <div className="space-y-5">
          <div className="border-b border-line pb-2.5">
            <h2 className="text-[20px] font-black text-ink tracking-tight uppercase">DATA PROVENANCE & METHODOLOGY</h2>
            <p className="text-[12px] text-ink-soft font-medium">Complete declaration of measured vs assumed data layers, standards, and caveats.</p>
          </div>
          <ProvenancePanel data={data} />
        </div>
      )}
    </AppShell>

    {/* Phase 5G — chat agent, hides itself when backend is unreachable (D16) */}
    <ChatPanel backendConnected={backendConnected} dataset={dataset} />
  );
}

function StageHeading({ stage, title, subtitle }: { stage: string; title: string; subtitle: string }) {
  return (
    <div className="border-b border-line pb-2 flex flex-wrap items-baseline justify-between gap-2">
      <div>
        <div className="text-[10px] font-black uppercase tracking-wider text-accent">
          {stage}
        </div>
        <h3 className="text-[17px] font-black text-ink leading-tight uppercase tracking-tight">
          {title}
        </h3>
        <p className="text-[12px] text-ink-soft font-medium">{subtitle}</p>
      </div>
    </div>
  );
}


