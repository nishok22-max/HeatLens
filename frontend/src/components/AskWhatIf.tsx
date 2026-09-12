import { useState } from "react";
import type { ReactNode } from "react";
import type { CoolingRow, Insights, SchedulingRow } from "../types";
import { API_ORIGIN } from "../data";
import { Note, Panel } from "./ui";
import { ask, EXAMPLE_QUESTIONS, type WhatIfResult } from "../whatif";

/**
 * Ask a what-if in any wording.
 *
 * TWO MODES, ONE GUARANTEE
 * ------------------------
 * With the API reachable, the question goes to the decision assistant
 * (POST /api/chat/whatif): an LLM reads any phrasing, maps it onto the levers
 * the physics models, compares options and recommends. It cannot invent a
 * number -- every figure must come from the pre-computed grid, and the server
 * post-checks that. Off-topic questions are declined.
 *
 * With the API unreachable (USB stick, wifi off), the rule parser below
 * answers exactly as before, from the grid compiled into this page. The panel
 * never depends on the network to work -- only to be clever.
 *
 * Falling back mid-session -- the assistant times out, the parser answers --
 * puts the panel into offline mode for that answer: offline label, offline
 * examples, and a line saying which of the two answered. The two modes accept
 * different phrasings, so a panel that still says "assistant" while the parser
 * is answering offers questions that are certain to be refused.
 */

interface AiScenario {
  cooling?: CoolingRow & { shade_pct: number; greening_pct: number };
  scheduling?: SchedulingRow;
  snaps?: { parameter: string; asked: string; used: string }[];
}

interface AiAnswer {
  answer: string;
  scenarios: AiScenario[];
  sources: string[];
  guard_passed: boolean;
  ungrounded_numbers: string[];
  refused: boolean;
  out_of_scope: boolean;
  model: string;
}

const AI_EXAMPLES = [
  "We can afford only one measure this week. What protects construction workers most?",
  "Is tarpaulin over work sites better than planting trees?",
  "Which neighbourhoods should get relief first, and what would help there?",
];

/** Why the assistant did not produce the answer on screen. A timeout is worth
 *  asking again; an unreachable API is not, until it is back. */
type FellBack = null | "timeout" | "error";

async function askAssistant(question: string, dataset: string): Promise<AiAnswer> {
  const controller = new AbortController();
  // The wait is the model's thinking time, not the network's. A comparison
  // question makes several tool rounds: ~40 s on gemini-2.0-flash, but 64 s
  // and then over 180 s for the SAME question on a large reasoning model,
  // measured two runs apart. 90 s sat in the middle of that spread, so it
  // aborted requests that would have answered and the panel refused at
  // random. Past this, the offline parser answers instead.
  const timer = setTimeout(() => controller.abort(), 240000);
  try {
    const res = await fetch(`${API_ORIGIN}/api/chat/whatif`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, dataset }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return (await res.json()) as AiAnswer;
  } finally {
    clearTimeout(timer);
  }
}

export function AskWhatIf({
  insights,
  backendConnected = false,
  dataset = "historical",
}: {
  insights: Insights;
  backendConnected?: boolean;
  dataset?: string;
}) {
  const [question, setQuestion] = useState("");
  const [rule, setRule] = useState<WhatIfResult | null>(null);
  const [ai, setAi] = useState<AiAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [fellBack, setFellBack] = useState<FellBack>(null);

  // The grid rides inside insights.json. If an older payload is being served,
  // hide the box rather than showing one that cannot answer.
  if (!insights.scenario_grid) return null;

  async function submit(text: string) {
    setQuestion(text);
    setAi(null);
    setRule(null);
    setFellBack(null);
    if (!text.trim()) return;

    if (backendConnected) {
      setLoading(true);
      try {
        setAi(await askAssistant(text, dataset));
        return;
      } catch (err) {
        // Answer offline instead of failing -- but record which failure it
        // was, because the two deserve different advice.
        const aborted = (err as { name?: string } | null)?.name === "AbortError";
        setFellBack(aborted ? "timeout" : "error");
      } finally {
        setLoading(false);
      }
    }
    setRule(ask(text, insights));
  }

  // The assistant and the parser take different phrasings. The parser refuses
  // anything that does not name a lever, so showing it the assistant's example
  // questions ("what protects construction workers most?") guarantees a
  // "Not recognised" -- the panel would be offering questions it knows it
  // cannot answer. After a fallback, show the parser's own examples instead.
  const assistantMode = backendConnected && fellBack === null;
  const examples = assistantMode ? AI_EXAMPLES : EXAMPLE_QUESTIONS;

  return (
    <Panel
      title="Ask your own what-if"
      subtitle={
        assistantMode
          ? "Ask in your own words. The decision assistant compares the modelled options and recommends one. Every number comes from the heat model."
          : "Offline mode: name a lever (work hours, shade or greening). Answers come from pre-computed physics."
      }
      right={
        <span className="text-[12px] text-ink-soft">
          {assistantMode ? "AI decision assistant" : "Offline parser"}
        </span>
      }
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
          placeholder={
            assistantMode
              ? "e.g. Should we shade sites or start work earlier for labourers?"
              : "e.g. shift work to 6am and shade 90%"
          }
          aria-label="Ask a what-if question"
          className="flex-1 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-[14px] text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-accent text-white px-5 py-2.5 text-[14px] font-semibold hover:opacity-90 transition-opacity shrink-0 disabled:opacity-60"
        >
          {loading ? "Thinking…" : "Ask"}
        </button>
      </form>

      <div className="flex flex-wrap gap-1.5 mt-2.5">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => submit(example)}
            disabled={loading}
            className="text-[12px] text-ink-soft bg-sunken/60 border border-line/60 rounded-md px-2.5 py-1 hover:border-accent/40 hover:text-ink transition-colors text-left"
          >
            {example}
          </button>
        ))}
      </div>

      {loading && (
        <p className="mt-4 text-[14px] text-ink-soft" role="status">
          Comparing the modelled options…
        </p>
      )}
      {fellBack && (
        <p className="mt-4 text-[13px] text-exercise">
          {fellBack === "timeout"
            ? "The decision assistant took too long to answer, so the offline parser answered instead. Asking again often works."
            : "The decision assistant could not be reached, so the offline parser answered instead."}{" "}
          The parser recognises only the modelled levers, so name one: work hours, shade or greening.
        </p>
      )}
      {ai && <AiResult result={ai} />}
      {rule && <Result result={rule} />}

      <Note>{insights.scenario_grid.basis}</Note>
    </Panel>
  );
}

function AiResult({ result }: { result: AiAnswer }) {
  if (result.out_of_scope || result.refused) {
    return (
      <div className="mt-4 rounded-xl border border-line bg-sunken/40 p-4">
        <div className="text-[13px] font-semibold text-ink mb-1">
          {result.out_of_scope ? "Outside what HeatLens covers" : "This is not a claim the project makes"}
        </div>
        <p className="text-[14px] leading-relaxed text-ink-soft">{result.answer}</p>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-accent/30 bg-accent-soft/30 p-4 space-y-4">
      <Markdown text={result.answer} />

      {result.scenarios.length > 0 && (
        <div className="border-t border-accent/20 pt-3">
          <div className="text-[12px] font-semibold text-ink-soft mb-2">
            Modelled results behind this answer
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            {result.scenarios.map((s, i) => (
              <div key={i} className="rounded-lg bg-surface border border-line p-3">
                {s.cooling && (
                  <Outcome
                    label="Felt heat at the peak hour"
                    before={`${s.cooling.utci_before} °C`}
                    after={`${s.cooling.utci_after} °C`}
                    delta={`${s.cooling.delta_c > 0 ? "+" : ""}${s.cooling.delta_c} °C`}
                    detail={
                      `${s.cooling.shade_pct}% shade` +
                      (s.cooling.greening_pct > 0
                        ? ` · ${s.cooling.greening_pct}% more greenery in ${s.cooling.zones_treated} zones`
                        : "")
                    }
                  />
                )}
                {s.scheduling && (
                  <Outcome
                    label={`Unsafe work hours · ${s.scheduling.persona}`}
                    before={`${s.scheduling.unsafe_before} h`}
                    after={`${s.scheduling.unsafe_after} h`}
                    delta={`−${s.scheduling.reduction_pct}%`}
                    detail={`Working day moved to ${s.scheduling.window}`}
                  />
                )}
                {s.snaps?.map((sn) => (
                  <div key={sn.parameter} className="text-[12px] text-exercise mt-1">
                    {sn.parameter}: asked {sn.asked}, nearest modelled value {sn.used}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-accent/20 pt-3 text-[12px] text-ink-faint space-y-0.5">
        <div>
          {result.guard_passed
            ? "Every number above was checked against the heat model's own output."
            : `Warning: some numbers could not be traced to the model (${result.ungrounded_numbers.join(", ")}). Treat them with caution.`}
        </div>
        <div>
          Written by {result.model}. Figures from {result.sources.join(", ") || "the scenario grid"}.
        </div>
      </div>
    </div>
  );
}

/** Just enough markdown for the assistant's format: bold and bullet lists.
 *  Rendered as React nodes, never as HTML, so model text cannot inject markup. */
function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc pl-5 space-y-1">
          {list.map((item, i) => (
            <li key={i}>{inline(item)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (/^[-*•]\s+/.test(line)) {
      list.push(line.replace(/^[-*•]\s+/, ""));
      continue;
    }
    flush();
    if (line) blocks.push(<p key={`p-${blocks.length}`}>{inline(line)}</p>);
  }
  flush();
  return <div className="text-[14px] leading-relaxed text-ink space-y-2">{blocks}</div>;
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
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
    return (
      <div className="mt-4 rounded-xl border border-line bg-sunken/40 p-4">
        <div className="text-[13px] font-semibold text-ink mb-1">
          {result.detail ?? REFUSAL_HEADING[result.refusalKind]}
        </div>
        <p className="text-[14px] leading-relaxed text-ink-soft">{result.reason}</p>
      </div>
    );
  }

  const { cooling, scheduling, snaps, matched, ambiguous } = result;
  const ambiguousKeys = Object.keys(ambiguous ?? {});
  return (
    <div className="mt-4 rounded-xl border border-accent/30 bg-accent-soft/30 p-4">
      {cooling && (
        <Outcome
          label="Felt heat at the peak hour"
          before={`${cooling.utci_before} °C`}
          after={`${cooling.utci_after} °C`}
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
          label={`Unsafe work hours · ${scheduling.persona}`}
          before={`${scheduling.unsafe_before} h`}
          after={`${scheduling.unsafe_after} h`}
          delta={`−${scheduling.reduction_pct}%`}
          detail={`Working day moved to ${scheduling.window}`}
        />
      )}

      {/* The trace. An answer whose provenance is not visible is not grounded,
          and this panel is the one place a number could look invented. */}
      <div className="mt-3 pt-3 border-t border-accent/20 text-[12px] leading-relaxed text-ink-faint space-y-1">
        <div>
          Matched {matched.join(", ")} and looked up a pre-computed grid row. No value was
          calculated in this browser.
        </div>
        {ambiguousKeys.map((key) => (
          <div key={key} className="text-exercise">
            You named more than one {key} value ({ambiguous[key].map((v) => formatSnap(v)).join(", ")}).
            The grid answers one at a time, so this result uses the first. Ask again for the other.
          </div>
        ))}
        {snaps.map((s) => (
          <div key={s.parameter} className="text-exercise">
            Snapped {s.parameter} from {formatSnap(s.asked)} to {formatSnap(s.used)}, the nearest
            value the grid holds. Nothing is interpolated between rows.
          </div>
        ))}
      </div>
    </div>
  );
}

function formatSnap(value: number | string): string {
  return typeof value === "number" && value <= 1 ? `${Math.round(value * 100)}%` : String(value);
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
      <div className="text-[12px] font-semibold text-accent mb-1">{label}</div>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[14px] text-ink-soft line-through decoration-ink-faint/50">{before}</span>
        <span className="text-ink-faint">→</span>
        <span className="text-[19px] font-bold text-ink">{after}</span>
        <span className="text-[12px] font-semibold text-ok bg-ok-bg border border-ok/40 rounded-md px-2 py-0.5">
          {delta}
        </span>
      </div>
      <div className="text-[13px] text-ink-soft mt-1">{detail}</div>
    </div>
  );
}
