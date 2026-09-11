import type { ReactNode } from "react";
import { useState } from "react";
import type { DatasetKey } from "../data";
import { DATASETS } from "../data";
import type { HeatData } from "../types";
import { weatherSource } from "../summary";

export type ViewKey =
  | "dashboard"
  | "map"
  | "work"
  | "scenarios"
  | "findings"
  | "advisory"
  | "data";

export const VIEWS: { key: ViewKey; label: string; hint: string }[] = [
  { key: "dashboard", label: "Overview", hint: "Today's situation and what to do" },
  { key: "map", label: "Heat map", hint: "Every neighbourhood, hour by hour" },
  { key: "work", label: "Work safety", hint: "Safe outdoor work hours" },
  { key: "scenarios", label: "What if", hint: "Test interventions" },
  { key: "advisory", label: "Public advisory", hint: "Warning message for SMS / WhatsApp" },
  { key: "findings", label: "Findings", hint: "Why neighbourhoods differ" },
  { key: "data", label: "Trust and data", hint: "Sources and limits" },
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

  const connection = backendLoading ? (
    <span>Checking for live data server…</span>
  ) : backendConnected ? (
    <span className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full bg-ok" aria-hidden /> Live data server connected
    </span>
  ) : (
    <span className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full bg-gold" aria-hidden /> Offline: using data built into this file
      {onRetryBackend && (
        <button onClick={onRetryBackend} className="underline hover:text-ink no-print">
          retry
        </button>
      )}
    </span>
  );

  return (
    <div className="min-h-screen w-full flex flex-col lg:flex-row bg-ground overflow-x-hidden">
      {/* Mobile header */}
      <div className="lg:hidden bg-charcoal text-[#FAF8F5] px-4 py-3 flex items-center justify-between no-print sticky top-0 z-40">
        <span className="text-[16px] font-bold">HeatLens</span>
        <button
          onClick={() => setMobileMenuOpen((v) => !v)}
          className="px-3 py-1.5 rounded-md bg-charcoal-surface text-[13px] border border-charcoal-border"
          aria-expanded={mobileMenuOpen}
        >
          {mobileMenuOpen ? "Close" : "Menu"}
        </button>
      </div>

      {/* Sidebar */}
      <aside
        className={`${
          mobileMenuOpen ? "block" : "hidden"
        } lg:block lg:w-64 shrink-0 bg-charcoal text-[#FAF8F5] lg:h-screen lg:sticky lg:top-0 overflow-y-auto no-print flex flex-col z-30`}
      >
        <div className="px-5 py-5 hidden lg:block border-b border-charcoal-border">
          <div className="text-[18px] font-bold tracking-tight">HeatLens</div>
          <div className="text-[12px] text-[#A3A099] mt-0.5">Heatwave early warning</div>
        </div>

        <nav aria-label="Main" className="px-3 py-4 flex-1">
          <ul className="flex flex-col gap-0.5">
            {VIEWS.map((v) => {
              const on = view === v.key;
              return (
                <li key={v.key}>
                  <button
                    onClick={() => {
                      onView(v.key);
                      setMobileMenuOpen(false);
                    }}
                    aria-current={on ? "page" : undefined}
                    className={`w-full text-left px-3 py-2 rounded-md transition-colors border-l-2 ${
                      on
                        ? "bg-charcoal-surface border-accent text-white"
                        : "border-transparent text-[#D4D1C9] hover:bg-charcoal-surface hover:text-white"
                    }`}
                  >
                    <span className={`block text-[14px] ${on ? "font-semibold" : ""}`}>{v.label}</span>
                    <span className="block text-[12px] text-[#8C8982] leading-snug">{v.hint}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="px-5 py-4 border-t border-charcoal-border text-[12px] leading-relaxed text-[#A3A099] space-y-1">
          <div className="text-[#E2E0D8]">{connection}</div>
          <div>Weather: {weatherSource(data)}</div>
          <div>Neighbourhoods: OpenStreetMap</div>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col min-h-screen w-full">
        {/* Exercise notice: stays, but calm */}
        <div className="bg-exercise-bg text-exercise border-b border-exercise/20 px-4 lg:px-8 py-1.5 text-[12px]">
          <strong className="font-semibold">Exercise</strong> · Not an official public alert.
          {isLive ? " Live weather forecast." : " Replay of the May 2010 heatwave."}
        </div>

        <header className="bg-surface border-b border-line px-4 lg:px-8 py-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-[22px] font-bold text-ink leading-tight tracking-tight">
                {data.meta.city}
              </h1>
              <p className="text-[13px] text-ink-soft mt-0.5 flex flex-wrap items-center gap-x-2">
                <span>
                  {data.meta.n_cells} neighbourhood zones · map at {hourLabel}
                </span>
                {isLive && data.meta.generated_at_ist && <span>· forecast updated {data.meta.generated_at_ist}</span>}
                <span className="lg:hidden text-ink-faint">· {connection}</span>
              </p>
            </div>

            <div className="flex gap-1 bg-sunken p-1 rounded-lg no-print" role="tablist" aria-label="Choose data">
              {(Object.keys(DATASETS) as DatasetKey[]).map((key) => {
                const on = dataset === key;
                return (
                  <button
                    key={key}
                    role="tab"
                    aria-selected={on}
                    onClick={() => onDataset(key)}
                    className={`px-3.5 py-1.5 rounded-md text-left transition-colors ${
                      on ? "bg-surface text-ink shadow-sm" : "text-ink-soft hover:text-ink"
                    }`}
                  >
                    <span className={`block text-[13px] whitespace-nowrap ${on ? "font-semibold" : ""}`}>
                      {DATASETS[key].label}
                    </span>
                    <span className="block text-[11px] text-ink-faint whitespace-nowrap">{DATASETS[key].sub}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </header>

        <main className="px-4 lg:px-8 py-6 flex-1 w-full max-w-[1500px]">{children}</main>
      </div>
    </div>
  );
}
