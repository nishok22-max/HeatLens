/**
 * The what-if matcher: text in, a pre-computed grid row out.
 *
 * WHAT THIS FILE IS NOT ALLOWED TO DO
 * ----------------------------------
 * It does not compute anything. No physics, no interpolation, no estimate. It
 * matches the question against rules that were authored and tested in
 * `src/heatstress/whatif.py`, then looks the answer up in a grid that
 * `src/heatstress/scenario_grid.py` computed during the bake.
 *
 * That constraint is what lets the simulator work with the wifi off. The rules
 * and the grid both ride inside `insights.json`, which is compiled into this
 * bundle at build time — so there is no API call to fail, and equally no way
 * for this file to invent a number the Python never produced.
 *
 * If a question does not match, it is refused. There is deliberately no
 * fallback that guesses.
 */
import type {
  CoolingRow,
  Insights,
  Intent,
  RefusalRule,
  SchedulingRow,
} from "./types";

export interface Snap {
  parameter: string;
  asked: number | string;
  used: number | string;
}

export interface WhatIfAnswer {
  kind: "answer";
  parameters: Record<string, number | string>;
  matched: string[];
  cooling?: CoolingRow;
  scheduling?: SchedulingRow;
  /** Values that had to move onto a grid point, so the UI can say so. */
  snaps: Snap[];
  /** Parameters the question named more than one value for. The grid answers
   *  one point at a time, so the extras are surfaced rather than dropped. */
  ambiguous: Record<string, number[]>;
}

export interface WhatIfRefusal {
  kind: "refusal";
  reason: string;
  refusalKind: "not_modelled" | "never_claim" | "unrecognised";
  detail?: string;
}

export type WhatIfResult = WhatIfAnswer | WhatIfRefusal;

const UNRECOGNISED =
  "That is not one of the levers this model can simulate. It can answer " +
  "questions about shifting outdoor work hours, shade over work areas, and " +
  "greening the hottest zones — try “shift work to 6am and shade 90%”.";

/** Nearest value on an axis. Never between two — see D20. */
function nearest<T extends number>(value: number, axis: T[]): T {
  return axis.reduce((best, candidate) =>
    Math.abs(candidate - value) < Math.abs(best - value) ? candidate : best,
  );
}

function applyTransform(
  intent: Intent,
  captured: string | undefined,
): number | string | null {
  switch (intent.transform) {
    case "hour": {
      const hour = Number(captured);
      return Number.isInteger(hour) && hour >= 0 && hour <= 23 ? hour : null;
    }
    case "percent": {
      const pct = Number(captured);
      return Number.isFinite(pct) && pct >= 0 && pct <= 100 ? pct / 100 : null;
    }
    case "default":
    case "literal":
      return intent.value ?? null;
    default:
      return null;
  }
}

export function ask(question: string, insights: Insights): WhatIfResult {
  const text = (question ?? "").trim().toLowerCase();
  const grid = insights.scenario_grid;
  const intents = insights.intents ?? [];
  const refusals = insights.refusals ?? [];

  if (!text || !grid || intents.length === 0) {
    return { kind: "refusal", reason: UNRECOGNISED, refusalKind: "unrecognised" };
  }

  // Refusals are checked first and win outright. Answering the modelled half of
  // "how many people are at risk if we add shade" would look like an answer to
  // the question that was actually asked.
  for (const rule of refusals as RefusalRule[]) {
    if (new RegExp(rule.pattern).test(text)) {
      const omitted = rule.omitted_item
        ? insights.omitted.find((o) => o.item === rule.omitted_item)
        : undefined;
      return {
        kind: "refusal",
        refusalKind: rule.kind,
        // Prefer the reason already on screen in the Omitted panel, so there is
        // one copy of it rather than two that can drift apart.
        reason: omitted?.why ?? rule.reason ?? UNRECOGNISED,
        detail: rule.omitted_item,
      };
    }
  }

  const parameters: Record<string, number | string> = {};
  const matched: string[] = [];
  const ambiguous: Record<string, number[]> = {};
  for (const intent of intents) {
    if (intent.parameter in parameters) continue; // explicit number wins
    const found = [...text.matchAll(new RegExp(intent.pattern, "g"))];
    if (found.length === 0) continue;
    const values: (number | string)[] = [];
    for (const m of found) {
      const value = applyTransform(intent, m[1]);
      if (value !== null && !values.includes(value)) values.push(value);
    }
    if (values.length === 0) continue;
    parameters[intent.parameter] = values[0];
    if (values.length > 1) ambiguous[intent.parameter] = values as number[];
    matched.push(intent.id);
  }

  // A persona on its own is not a what-if. "What if we give workers more
  // breaks" contains "workers"; answering it with a shift-hours result would
  // answer a question nobody asked. A lever must be named.
  const LEVERS = ["shift_start", "shade", "greening"];
  if (!LEVERS.some((l) => l in parameters)) {
    return { kind: "refusal", reason: UNRECOGNISED, refusalKind: "unrecognised" };
  }

  const snaps: Snap[] = [];
  const answer: WhatIfAnswer = { kind: "answer", parameters, matched, snaps, ambiguous };

  if ("shade" in parameters || "greening" in parameters) {
    const askedShade = (parameters.shade as number) ?? 0;
    const askedGreen = (parameters.greening as number) ?? 0;
    const shade = nearest(askedShade, grid.axes.shade);
    const greening = nearest(askedGreen, grid.axes.greening);
    if (shade !== askedShade)
      snaps.push({ parameter: "shade", asked: askedShade, used: shade });
    if (greening !== askedGreen)
      snaps.push({ parameter: "greening", asked: askedGreen, used: greening });
    answer.cooling = grid.cooling.find(
      (r) => r.shade === shade && r.greening === greening,
    );
  }

  if ("shift_start" in parameters) {
    const askedStart = parameters.shift_start as number;
    const start = nearest(askedStart, grid.axes.shift_start);
    const persona = (parameters.persona as string) ?? grid.axes.persona[0];
    if (start !== askedStart)
      snaps.push({ parameter: "shift_start", asked: askedStart, used: start });
    answer.scheduling = grid.scheduling.find(
      (r) => r.shift_start === start && r.persona === persona,
    );
  }

  if (!answer.cooling && !answer.scheduling) {
    return { kind: "refusal", reason: UNRECOGNISED, refusalKind: "unrecognised" };
  }
  return answer;
}

export const EXAMPLE_QUESTIONS = [
  "shift work to 6am and shade 90%",
  "what if we plant trees in the hottest wards",
  "50% shade for delivery riders",
  "how many people are at risk",
];
