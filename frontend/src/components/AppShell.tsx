import type { ReactNode } from "react";
import { useState } from "react";
import type { DatasetKey } from "../data";
import { DATASETS } from "../data";
import type { HeatData } from "../types";

export type ViewKey =
  | "dashboard"
  | "map"
  | "work"
  | "scenarios"
  | "findings"
  | "advisory"
  | "data";

export const VIEWS: { key: ViewKey; label: string; icon: string; hint: string }[] = [
  { key: "dashboard", label: "OVERVIEW", icon: "▦", hint: "Current heat situation & decision chain" },
  { key: "map", label: "RISK MAP", icon: "◈", hint: "Hyperlocal H3 risk & microclimates" },
  { key: "work", label: "WORK SAFETY", icon: "◷", hint: "Outdoor worker safety windows (ISO 7243)" },
  { key: "scenarios", label: "SCENARIOS", icon: "⇄", hint: "What-if intervention simulator" },
  { key: "findings", label: "FINDINGS", icon: "◲", hint: "UHI patterns & night cooling deficit" },
  { key: "advisory", label: "ADVISORY", icon: "◔", hint: "Public warning messages (CAP 1.2)" },
  { key: "data", label: "DATA & LIMITS", icon: "◑", hint: "Provenance, resolution & model caveats" },
];

export function AppShell({
  data,
  dataset,
  onDataset,
  view,
  onView,
  hourLabel,
  backendConnected = false,
  backendLoading = false,
  onRetryBackend,
  children,
}: {
  data: HeatData;
  dataset: DatasetKey;
  onDataset: (k: DatasetKey) => void;
  view: ViewKey;
  onView: (v: ViewKey) => void;
  hourLabel: string;
  backendConnected?: boolean;
  backendLoading?: boolean;
  onRetryBackend?: () => void;
  children: ReactNode;
}) {
  const isLive = data.meta.mode === "live";
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen w-full flex flex-col lg:flex-row bg-ground overflow-x-hidden">
      {/* ---- Mobile Header Navigation Bar --------------------------------- */}
      <div className="lg:hidden bg-[#181816] text-[#FAF8F5] px-4 py-3 border-b border-[#2B2A26] flex items-center justify-between no-print sticky top-0 z-40 shadow-md">
        <div className="flex items-center gap-2.5">
          <span
            className="w-8 h-8 rounded-lg grid place-items-center text-white text-[15px] shrink-0 bg-accent shadow-sm"
            aria-hidden
          >
            🛡️
          </span>
          <div>
            <span className="block text-[14px] font-black tracking-tight leading-none uppercase text-[#FAF8F5]">
              HeatLens
            </span>
            <span className="text-[9px] text-[#A3A099] font-medium leading-none">
              Public Health Intelligence
            </span>
          </div>
        </div>
        <button
          onClick={() => setMobileMenuOpen((v) => !v)}
          className="px-3 py-1.5 rounded-lg bg-[#242320] text-[#E2E0D8] text-[12px] font-bold border border-[#36342F] hover:bg-[#2E2C28]"
          aria-expanded={mobileMenuOpen}
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? "Close ✕" : "Menu ☰"}
        </button>
      </div>

      {/* ---- Warm Charcoal Command-Centre Sidebar (#181816) --------------- */}
      <aside
        className={`${
          mobileMenuOpen ? "block" : "hidden"
        } lg:block lg:w-72 shrink-0 bg-[#181816] text-[#FAF8F5] border-b lg:border-b-0 lg:border-r border-[#2B2A26] lg:h-screen lg:sticky lg:top-0 overflow-y-auto no-print shadow-xl flex flex-col z-30`}
      >
        <div className="px-5 py-4.5 hidden lg:flex items-center gap-3 border-b border-[#2B2A26] bg-[#141412] shrink-0">
          <span
            className="w-9 h-9 rounded-lg grid place-items-center text-white text-[17px] shrink-0 bg-accent shadow-sm"
            aria-hidden
          >
            🛡️
          </span>
          <span className="min-w-0">
            <span className="flex items-center gap-1.5">
              <span className="block text-[16px] font-black tracking-tight leading-tight text-[#FAF8F5] uppercase">
                HeatLens
              </span>
              <span className="px-1.5 py-0.2 bg-teal/20 text-teal-soft text-[9px] font-extrabold rounded uppercase border border-teal/40">
                SIH
              </span>
            </span>
            <span className="block text-[10px] font-medium text-[#A3A099] leading-tight mt-0.5">
              Heatwave Early Warning Intelligence
            </span>
          </span>
        </div>

        <nav aria-label="Main Navigation" className="px-3 py-4 flex-1">
          <div className="text-[10px] uppercase tracking-wider font-extrabold text-[#A3A099] px-3 mb-2.5">
            System Modules
          </div>
          <ul className="flex flex-col gap-1">
            {VIEWS.map((v) => {
              const on = view === v.key;
              return (
                <li key={v.key} className="shrink-0">
                  <button
                    onClick={() => {
                      onView(v.key);
                      setMobileMenuOpen(false);
                    }}
                    aria-current={on ? "page" : undefined}
                    className={`w-full text-left px-3 py-2 rounded-lg transition-colors border-l-4 ${
                      on
                        ? "bg-[#282723] border-accent text-[#FAF8F5] font-bold"
                        : "border-transparent text-[#D4D1C9] hover:bg-[#242320] hover:text-[#FAF8F5]"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`text-[14px] ${on ? "text-accent" : "text-[#8C8982]"}`}
                        aria-hidden
                      >
                        {v.icon}
                      </span>
                      <span className="text-[12px] font-extrabold uppercase tracking-wide leading-tight">
                        {v.label}
                      </span>
                    </div>
                    <span
                      className={`block text-[10px] font-medium leading-snug mt-0.5 pl-6 ${
                        on ? "text-[#C4C0B6]" : "text-[#8C8982]"
                      }`}
                    >
                      {v.hint}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="hidden lg:block px-4 py-3.5 border-t border-[#2B2A26] bg-[#141412] shrink-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`w-2 h-2 rounded-full ${
                backendConnected ? "bg-ok animate-pulse" : "bg-gold"
              }`}
            />
            <span className="text-[11px] font-bold text-[#FAF8F5]">
              {backendConnected ? "Backend API: Connected" : "Backend API: Offline Mode"}
            </span>
          </div>
          <p className="text-[10px] leading-relaxed text-[#A3A099] font-medium">
            Physical thermal modeling (UTCI & WBGT) using ERA5 and H3 grid geometry. Built for decision support & emergency public health response.
          </p>
        </div>
      </aside>

      {/* ---- Main Content Area (Full Available Viewport Width) ------------- */}
      <div className="flex-1 min-w-0 flex flex-col min-h-screen w-full">
        {/* Exercise Banner */}
        <div className="bg-exercise-bg border-b border-exercise/30 px-4 lg:px-8 py-2 flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-2">
            <span className="inline-block px-2 py-0.5 rounded bg-exercise text-white text-[9px] font-black uppercase tracking-wider shadow-2xs">
              Simulation Mode
            </span>
            <p className="text-[11px] font-semibold text-exercise">
              EXERCISE MODE — Not an official issued public alert ·{" "}
              {isLive ? "Live weather forecast model" : "Historical disaster replay (May 2010)"}
            </p>
          </div>
          <span className="text-[10px] font-mono font-bold text-exercise/90 hidden sm:inline">
            CAP 1.2 Status: EXERCISE
          </span>
        </div>

        {/* Command Top Header Bar */}
        <header className="bg-surface border-b border-line px-4 lg:px-8 py-3.5 shadow-2xs shrink-0">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-[20px] font-black text-ink leading-tight tracking-tight">
                  {data.meta.city}, Gujarat
                </h1>
                <span className="px-2.5 py-0.5 rounded-full bg-accent-soft text-accent text-[11px] font-extrabold border border-accent/20">
                  {data.meta.n_cells} H3 Neighbourhood Zones
                </span>

                {/* Backend Connection Status Badge */}
                {backendLoading ? (
                  <span className="px-2.5 py-0.5 rounded-full bg-accent-soft text-accent text-[11px] font-extrabold border border-accent/30 flex items-center gap-1.5 animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-accent animate-ping" />
                    Fetching API Data…
                  </span>
                ) : backendConnected ? (
                  <span
                    className="px-2.5 py-0.5 rounded-full bg-ok-bg text-ok text-[11px] font-black border border-ok/30 flex items-center gap-1.5"
                    title="Connected to Python REST API server on http://localhost:8000"
                  >
                    <span className="w-2 h-2 rounded-full bg-ok animate-pulse" />
                    BACKEND STATUS: ● CONNECTED
                  </span>
                ) : (
                  <button
                    onClick={onRetryBackend}
                    className="px-2.5 py-0.5 rounded-full bg-exercise-bg text-exercise text-[11px] font-extrabold border border-exercise/40 flex items-center gap-1.5 hover:bg-exercise/20 transition-colors"
                    title="Click to retry connecting to Python REST API server on http://localhost:8000"
                  >
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    BACKEND STATUS: ○ OFFLINE — USING DEMO DATA <span className="underline ml-1">Retry ↻</span>
                  </button>
                )}
              </div>
              <p className="text-[12px] text-ink-soft mt-0.5 flex items-center gap-2 flex-wrap font-medium">
                <span>{data.meta.focus.date}</span>
                <span>•</span>
                <span className="font-bold text-ink">{hourLabel} IST</span>
                {isLive && data.meta.generated_at_ist && (
                  <>
                    <span>•</span>
                    <span className="text-ok flex items-center gap-1 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-ok animate-ping" />
                      Forecast updated {data.meta.generated_at_ist}
                    </span>
                  </>
                )}
              </p>
            </div>

            {/* Dataset Scenario Switcher Tabs */}
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-extrabold uppercase tracking-wider text-ink-faint hidden md:inline">
                Data Scenario:
              </span>
              <div
                className="flex gap-1 bg-sunken p-1 rounded-xl no-print border border-line-strong/40"
                role="tablist"
                aria-label="Choose dataset period"
              >
                {(Object.keys(DATASETS) as DatasetKey[]).map((key) => {
                  const on = dataset === key;
                  return (
                    <button
                      key={key}
                      role="tab"
                      aria-selected={on}
                      onClick={() => onDataset(key)}
                      className={`px-3.5 py-1.5 rounded-lg text-left transition-all ${
                        on
                          ? "bg-surface text-ink shadow-sm font-extrabold border border-line/60"
                          : "text-ink-soft hover:text-ink hover:bg-surface/60 font-semibold"
                      }`}
                    >
                      <span className="block text-[12px] whitespace-nowrap">
                        {DATASETS[key].label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </header>

        <main className="px-4 lg:px-8 py-6 flex-1 w-full max-w-none">{children}</main>
      </div>
    </div>
  );
}


