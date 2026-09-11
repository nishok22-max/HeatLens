import { useState } from "react";
import type { HeatData } from "../types";
import { Badge, Note, Panel } from "./ui";

const LANGUAGE_NAMES: Record<string, string> = {
  en: "English Broadcast",
  hi: "हिन्दी (Hindi Warning)",
  gu: "ગુજરાતી (Gujarati Warning)",
};

export function AdvisoryPanel({ data }: { data: HeatData }) {
  const a = data.advisory;
  const [language, setLanguage] = useState("en");
  const [showCap, setShowCap] = useState(false);
  const verified = a.languages_verified[language] ?? false;

  return (
    <Panel
      title="Warning message"
      subtitle={`Automated emergency alert copy generated for the worst-affected zone on ${data.meta.focus.date}`}
      right={<Badge tone="flag">{a.severity}</Badge>}
    >
      {/* Language Pills */}
      <div className="flex flex-wrap gap-2 mb-4 no-print">
        {Object.keys(a.text).map((code) => (
          <button
            key={code}
            onClick={() => setLanguage(code)}
            className={`px-3.5 py-1.5 text-[12px] font-extrabold border rounded-xl transition-all ${
              language === code
                ? "bg-accent text-white border-accent shadow-xs"
                : "bg-surface text-ink-soft border-line hover:border-line-strong hover:bg-sunken font-semibold"
            }`}
          >
            {LANGUAGE_NAMES[code] ?? code}
            {!a.languages_verified[code] && (
              <span className="ml-1 text-[10px] text-amber-500 font-bold" title="Unverified machine translation">
                ⚠️
              </span>
            )}
          </button>
        ))}
      </div>

      {!verified && (
        <div className="mb-3.5 p-3.5 bg-flag-bg border border-flag/30 rounded-xl shadow-2xs">
          <p className="text-[12px] text-flag leading-snug font-semibold flex items-center gap-2">
            <span className="text-[16px]">⚠️</span>
            <span><strong className="font-black">Unverified Translation Warning:</strong> This text is machine-translated and requires official human verification prior to public broadcast.</span>
          </p>
        </div>
      )}

      <blockquote className="border-l-4 border-accent bg-accent-soft/50 p-4.5 rounded-r-2xl text-[14px] leading-relaxed text-ink font-semibold shadow-2xs">
        "{a.text[language]}"
      </blockquote>

      <div className="mt-4.5 p-3.5 bg-sunken/60 border border-line/80 rounded-xl">
        <div className="text-[10px] uppercase font-black tracking-wider text-ink-faint">
          Operational Directive for Public Health Officials
        </div>
        <div className="text-[12px] text-ink font-extrabold mt-0.5">{a.safe_work_note}</div>
      </div>

      <button
        onClick={() => setShowCap((v) => !v)}
        className="mt-4 text-[12px] font-black text-accent hover:underline no-print flex items-center gap-1.5"
      >
        <span>{showCap ? "▲ Hide" : "▼ Show"} OASIS CAP 1.2 Emergency XML Payload</span>
      </button>

      {showCap && (
        <div className="mt-2.5">
          <pre className="text-[11px] leading-tight bg-slate-900 text-slate-100 border border-slate-700 rounded-xl p-3.5 overflow-x-auto max-h-72 font-mono shadow-inner">
            {a.cap_xml}
          </pre>
          <Note>
            Formatted in accordance with OASIS Common Alerting Protocol (CAP 1.2) standard for seamless integration with NDMA / SAKSHAM alert channels.
          </Note>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-line">
        <Badge tone="warn">status = Exercise</Badge>
        <Badge tone="neutral">not dispatched</Badge>
        <Badge tone="flag">hi / gu unverified</Badge>
      </div>
    </Panel>
  );
}


