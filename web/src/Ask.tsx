import { useState, type RefObject } from "react";
import type { AskResult, AskStep } from "./api";

// Each was checked against the data (2026-10-24) to return jobs: an example that finds
// nothing shows the feature failing.
export const EXAMPLES = [
  "Entry-level backend jobs in Bengaluru that use FastAPI or Django",
  "Entry DevOps jobs that mention Kubernetes, paying at least my minimum",
  "Which internships mentioning Docker or Kubernetes suit my skills best, and why?",
];

const STOPPED: Record<AskResult["stopped"], string> = {
  answered: "answered", step_limit: "stopped at the step limit",
  token_budget: "stopped at the token budget", error: "stopped: model service error",
};

/** The question box that takes the search box's place in the Ask view. */
export function AskBar({ value, onChange, onAsk, busy, inputRef }: {
  value: string; onChange: (v: string) => void; onAsk: (q: string) => void; busy: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  const ready = value.trim().length >= 3 && !busy;
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (ready) onAsk(value); }} className="flex w-full max-w-[680px] flex-1 items-center gap-1.5">
      <input
        ref={inputRef} value={value} onChange={(e) => onChange(e.target.value)} maxLength={500}
        placeholder="Ask about your jobs, e.g. remote backend roles above my minimum pay"
        className="h-7 min-w-0 flex-1 rounded-[3px] border border-rule bg-sheet px-2 text-[12.5px] outline-none placeholder:text-faint focus:border-soft"
      />
      <button
        type="submit" disabled={!ready}
        className={`h-7 rounded-[3px] border px-2.5 text-[12.5px] ${ready ? "border-mark bg-mark text-sheet" : "border-rule text-faint"}`}
      >
        {busy ? "Asking…" : "Ask"}
      </button>
    </form>
  );
}

/** The answer above the table: the text, one line of facts, and the steps on request. */
export function AskAnswer({ result, error, busy, onExample }: {
  result: AskResult | null; error: string; busy: boolean; onExample: (q: string) => void;
}) {
  const [showSteps, setShowSteps] = useState(false);
  if (error) return <p className="border-b border-rule px-3 py-2 text-[12.5px] text-bad">{error}</p>;
  if (!result) {
    if (busy) return null;
    return (
      <div className="border-b border-rule px-3 py-2.5 text-[12.5px] text-soft">
        <p className="max-w-[80ch]">
          Ask in plain words. The agent searches your jobs with the table's own filters, reads the few it compares,
          and puts the ones it picks in the table below. It can only read: nothing is changed.
        </p>
        <div className="mt-1.5 flex flex-col items-start gap-0.5">
          {EXAMPLES.map((q) => (
            <button key={q} onClick={() => onExample(q)} className="text-left text-ink underline decoration-rule underline-offset-2 hover:decoration-soft">{q}</button>
          ))}
        </div>
      </div>
    );
  }
  const calls = result.steps.filter((s) => s.kind === "model").length;
  return (
    <div className="border-b border-rule px-3 py-2">
      <p className="max-w-[80ch] text-[13px] leading-relaxed text-ink">{result.answer}</p>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11.5px] text-faint">
        <span className="num">
          {calls} {calls === 1 ? "call" : "calls"} · {result.seconds}s · {(result.tokens_in + result.tokens_out).toLocaleString("en-IN")} tokens
        </span>
        <span className={result.stopped === "answered" ? "" : "text-warn"}>· {STOPPED[result.stopped]}</span>
        <button onClick={() => setShowSteps(!showSteps)} className="underline underline-offset-2 hover:text-ink">
          {showSteps ? "Hide steps" : "Steps"}
        </button>
      </div>
      {showSteps && (
        <ol className="thin num mt-1.5 max-h-[35vh] space-y-0.5 overflow-y-auto text-[11.5px]">
          {result.steps.map((s, i) => <StepLine key={i} step={s} />)}
        </ol>
      )}
    </div>
  );
}

function StepLine({ step }: { step: AskStep }) {
  switch (step.kind) {
    case "model":
      return <li className="pt-1 text-faint">call {step.step} · {step.model} · {step.tokens_in ?? "?"} in / {step.tokens_out ?? "?"} out · {step.seconds}s</li>;
    case "tool":
      return (
        <li className={`truncate pl-3 ${step.failed ? "text-bad" : "text-soft"}`} title={step.result}>
          {step.tool}({step.arguments}) → {step.result}
        </li>
      );
    case "answer":
      return <li className="pl-3 text-soft">give_answer → {step.job_ids.length} {step.job_ids.length === 1 ? "job" : "jobs"}</li>;
    case "error":
      return <li className="pl-3 text-bad">service error: {step.error}</li>;
  }
}
