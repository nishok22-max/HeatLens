import type { ReactNode } from "react";
import type { Verdict } from "../plain";
import { TONE_COLOUR } from "../metrics";

/** A titled panel. The basic unit of the console layout. */
export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
}: {
  title: string;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card overflow-hidden ${className}`}>
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-line/80 bg-surface/60">
        <div className="min-w-0 flex-1">
          <h2 className="text-[16px] font-bold text-ink leading-tight tracking-tight">
            {title}
          </h2>
          {subtitle && (
            <p className="text-[13px] text-ink-soft mt-0.5 leading-snug">
              {subtitle}
            </p>
          )}
        </div>
        {right && <div className="shrink-0 no-print">{right}</div>}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

type Tone = "neutral" | "ok" | "warn" | "flag" | "accent";

const TONES: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-soft border-line-strong/60 font-bold",
  ok: "bg-ok-bg text-ok border-ok/30 font-black",
  warn: "bg-exercise-bg text-exercise border-exercise/30 font-black",
  flag: "bg-flag-bg text-flag border-flag/30 font-black",
  accent: "bg-accent-soft text-accent border-accent/25 font-black",
};

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[10px] uppercase tracking-wider border rounded-lg shadow-2xs ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/**
 * Maps a provenance `status` string to a visual tone.
 */
export function statusTone(status: string): Tone {
  const s = status.toLowerCase();
  if (s.startsWith("measured")) return "ok";
  if (s.startsWith("published")) return "ok";
  // Computed is not measured, but it is not a weakness either: deterministic
  // physics from published equations, cross-checked against a second
  // implementation. It earns the same tone as an observation.
  if (s.startsWith("computed")) return "ok";
  // A forecast is inherently uncertain, but that is the nature of forecasting,
  // not a defect in the data. Distinct tone, deliberately not alarming.
  if (s.startsWith("predicted")) return "accent";
  if (s.includes("not fitted") || s.includes("not calibrated")) return "flag";
  if (s.includes("assumed")) return "warn";
  return "warn";
}

/** A plain-language heat level, always as colour AND words. */
export function LevelChip({
  verdict,
  size = "sm",
}: {
  verdict: Verdict;
  size?: "sm" | "lg";
}) {
  const c = TONE_COLOUR[verdict.tone];
  return (
    <span
      className={`inline-flex items-center rounded-md font-bold whitespace-nowrap ${
        size === "lg" ? "px-3 py-1 text-[15px]" : "px-2 py-0.5 text-[12px]"
      }`}
      style={{ background: c.bg, color: c.ink }}
    >
      {verdict.label}
    </span>
  );
}

/** Label/value row for readouts. */
export function Row({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-line/60 last:border-0 hover:bg-sunken/30 px-2 rounded-lg transition-colors">
      <span className="text-[12px] text-ink-soft font-medium" title={hint}>
        {label}
      </span>
      <span className="text-[13px] font-extrabold tnum text-ink">{value}</span>
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] leading-relaxed text-ink-faint mt-2.5 flex items-start gap-1.5 font-medium">
      <span className="shrink-0 text-[11px] font-bold text-accent">ℹ</span>
      <span>{children}</span>
    </p>
  );
}


