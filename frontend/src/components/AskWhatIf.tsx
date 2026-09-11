import { useState } from "react";
import type { Insights } from "../types";
import { Note, Panel } from "./ui";
import { ask, EXAMPLE_QUESTIONS, type WhatIfResult } from "../whatif";

/**
 * Ask a what-if in plain English.
 *
 * This is a parser with a text box, not a chatbot. It recognises the three
 * levers the physics can model, looks the answer up in a grid computed during
 * the bake, and refuses everything else. Every number shown here was produced
 * by `insight.py`; none of it is calculated in the browser, which is why it
 * still answers with the network off.
 */
export function AskWhatIf({ insights }: { insights: Insights }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<WhatIfResult | null>(null);

  // The grid rides inside insights.json. If an older payload is being served,
  // hide the box rather than showing one that cannot answer.
  if (!insights.scenario_grid) return null;

  function submit(text: string) {
    setQuestion(text);
    setResult(text.trim() ? ask(text, insights) : null);
  }

  return (
    <Panel
      title="ASK A WHAT-IF"
      subtitle="Type a question in plain English — answers come from pre-computed physics, never generated text"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
        className="flex flex-col sm:flex-row gap-2"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. shift work to 6am and shade 90%"
          aria-label="Ask a what-if question"
          className="flex-1 rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[13px] text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
        />
        <button
          type="submit"
          className="rounded-xl bg-accent text-white px-5 py-2.5 text-[12px] font-black uppercase tracking-wider hover:opacity-90 transition-opacity shrink-0"
        >
          Simulate
        </button>
      </form>

      <div className="flex flex-wrap gap-1.5 mt-2.5">
        {EXAMPLE_QUESTIONS.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => submit(example)}
            className="text-[11px] font-semibold text-ink-soft bg-sunken/60 border border-line/60 rounded-lg px-2.5 py-1 hover:border-accent/40 hover:text-ink transition-colors"
          >
            {example}
          </button>
        ))}
      </div>

      {result && <Result result={result} />}

      <Note>
        {insights.scenario_grid.basis}
      </Note>
    </Panel>
  );
}

/** Why the question was refused. A headcount question and an unparseable one
 *  are different refusals, and labelling both "not a modelled lever" would
 *  misdescribe the second. */
const REFUSAL_HEADING: Record<string, string> = {
  not_modelled: "Not a modelled lever",
  never_claim: "This is not a claim the project makes",
  unrecognised: "Not recognised",
};

function Result({ result }: { result: WhatIfResult }) {
  if (result.kind === "refusal") {
    const isNeverClaim = result.refusalKind === "never_claim";
    return (
      <div
        className={`mt-4 rounded-xl border p-4 ${
          isNeverClaim
            ? "border-warn/40 bg-warn-bg/50"
            : "border-line bg-sunken/40"
        }`}
      >
        <div className="text-[10px] font-black uppercase tracking-wider text-ink-faint mb-1.5">
          {result.detail ?? REFUSAL_HEADING[result.refusalKind]}
        </div>
        <p className="text-[13px] leading-relaxed text-ink-soft font-medium">
          {result.reason}
        </p>
      </div>
    );
  }

  const { cooling, scheduling, snaps, matched, ambiguous } = result;
  const ambiguousKeys = Object.keys(ambiguous ?? {});
  return (
    <div className="mt-4 rounded-xl border border-accent/30 bg-accent-soft/30 p-4">
      {cooling && (
        <Outcome
          label="Felt temperature at the peak hour"
          before={`${cooling.utci_before} °C felt`}
          after={`${cooling.utci_after} °C felt`}
          delta={`${cooling.delta_c > 0 ? "+" : ""}${cooling.delta_c} °C`}
          detail={
            `${Math.round(cooling.shade * 100)}% shade` +
            (cooling.greening > 0
              ? ` · ${Math.round(cooling.greening * 100)}% more greenery in ${cooling.zones_treated} zones`
              : "")
          }
        />
      )}

      {scheduling && (
        <Outcome
          label={`Unsafe working hours · ${scheduling.persona}`}
          before={`${scheduling.unsafe_before}h unsafe`}
          after={`${scheduling.unsafe_after}h unsafe`}
          delta={`−${scheduling.reduction_pct}%`}
          detail={`Working day moved to ${scheduling.window}`}
        />
      )}

      {/* The trace. An answer whose provenance is not visible is not grounded,
          and this panel is the one place a number could look invented. */}
      <div className="mt-3 pt-3 border-t border-accent/20 text-[11px] leading-relaxed text-ink-faint font-medium space-y-1">
        <div>
          <span className="font-black uppercase tracking-wider">Trace:</span>{" "}
          matched {matched.join(", ")} → looked up a pre-computed grid row. No
          value was calculated in this browser.
        </div>
        {ambiguousKeys.map((key) => (
          <div key={key} className="text-warn">
            You named more than one {key} value (
            {ambiguous[key].map((v) => formatSnap(v)).join(", ")}). The grid
            answers one at a time — this result uses the first. Ask again for
            the other to compare.
          </div>
        ))}
        {snaps.map((s) => (
          <div key={s.parameter} className="text-warn">
            Snapped {s.parameter} from {formatSnap(s.asked)} to{" "}
            {formatSnap(s.used)} — the nearest value the grid holds. Nothing is
            interpolated between rows.
          </div>
        ))}
      </div>
    </div>
  );
}

function formatSnap(value: number | string): string {
  return typeof value === "number" && value <= 1
    ? `${Math.round(value * 100)}%`
    : String(value);
}

function Outcome({
  label,
  before,
  after,
  delta,
  detail,
}: {
  label: string;
  before: string;
  after: string;
  delta: string;
  detail: string;
}) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="text-[10px] font-black uppercase tracking-wider text-accent mb-1.5">
        {label}
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[13px] font-bold text-ink-soft line-through decoration-ink-faint/50">
          {before}
        </span>
        <span className="text-ink-faint">→</span>
        <span className="text-[19px] font-black text-ink">{after}</span>
        <span className="text-[12px] font-black text-ok bg-ok-bg border border-ok/40 rounded-md px-2 py-0.5">
          {delta}
        </span>
      </div>
      <div className="text-[12px] text-ink-soft font-medium mt-1">{detail}</div>
    </div>
  );
}
