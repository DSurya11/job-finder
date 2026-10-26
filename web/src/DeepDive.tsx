import { useEffect, useState } from "react";
import { fetchDeepDive, startDeepDive, type DeepDive as Report, type DeepDiveItem } from "./api";

/**
 * One job researched before applying. The agent reads the posting, the user's profile and resume
 * and up to 3 pages of the company's own site; code keeps only the items whose quote is really in
 * their source. Runs in the background (a live one took 166 s), so this polls until it is done.
 */
export default function DeepDive({ jobId }: { jobId: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [check, setCheck] = useState(0);         // bumped to start checking again after Start

  useEffect(() => { setReport(null); setRunning(false); setError(null); }, [jobId]);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const state = await fetchDeepDive(jobId);
        if (!live) return;
        setReport(state.deepdive);
        setRunning(state.running);
        setError(state.error);
        if (state.running) timer = setTimeout(poll, 3000);
      } catch {
        if (live) timer = setTimeout(poll, 5000);
      }
    };
    void poll();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [jobId, check]);

  async function start() {
    setError(null);
    try {
      await startDeepDive(jobId);
      setRunning(true);
      setCheck((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the research.");
    }
  }

  return (
    <section className="mt-8 border-t border-rule pt-5">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <div className="label">Deep dive</div>
          <p className="mt-1 text-[13px] text-soft">
            Why you fit, what is missing, resume bullets for this job and a referral draft. Every line quotes its source.
          </p>
        </div>
        <button
          onClick={start}
          disabled={running}
          className="h-8 shrink-0 rounded-[4px] border border-rule px-3 text-[13px] text-ink hover:border-soft disabled:opacity-60"
        >
          {running ? "Researching…" : report ? "Research again" : "Research this job"}
        </button>
      </div>

      {running && (
        <p className="mt-3 text-[13px] text-soft">
          Reading the posting, your resume and the company's own site. Usually 1 to 3 minutes on the free models.
        </p>
      )}
      {error && <p className="mt-3 text-[13px] text-bad">{error}</p>}

      {report && (
        <div className="mt-4 space-y-6 text-[14px]">
          <Items title="Why you fit" items={report.report.strengths} label={(i) => (i.source === "profile" ? "Your profile" : "Your resume")} />
          <Items title="What the job asks that you do not show" items={report.report.gaps} label={() => "The posting"} />
          <Items title="Resume bullets for this job" items={report.report.bullets} label={() => "Based on your resume"} copy />
          <Items
            title="About the company"
            items={report.report.company}
            label={(i) => {
              const page = report.pages.find((p) => p.id === i.source);
              return page ? new URL(page.url).hostname + new URL(page.url).pathname : i.source;
            }}
            href={(i) => report.pages.find((p) => p.id === i.source)?.url}
          />

          {report.report.message && (
            <div>
              <div className="flex items-baseline justify-between">
                <div className="label">Referral message (a draft: edit it before sending)</div>
                <CopyButton text={report.report.message} />
              </div>
              <p className="mt-1.5 whitespace-pre-wrap leading-relaxed">{report.report.message}</p>
              {(report.report.message_unverified?.length ?? 0) > 0 && (
                <p className="mt-1.5 text-[12.5px] text-warn">
                  Check before sending: {report.report.message_unverified!.join(", ")} (not in your resume, profile or the posting).
                </p>
              )}
            </div>
          )}

          <footer className="border-t border-rule pt-3 text-[12px] text-faint">
            {report.dropped.length > 0 && (
              <details className="mb-1.5">
                <summary className="cursor-pointer text-soft">
                  {report.dropped.length} item{report.dropped.length > 1 ? "s" : ""} removed: not supported by their sources
                </summary>
                <ul className="mt-1.5 space-y-1">
                  {report.dropped.map((d, i) => (
                    <li key={i}><span className="text-soft">{d.text}</span> · {d.reason}</li>
                  ))}
                </ul>
              </details>
            )}
            {report.pages.length > 0 && (
              <div>Read: {report.pages.map((p, i) => (
                <span key={p.id}>{i > 0 && " · "}<a href={p.url} target="_blank" rel="noopener" className="underline underline-offset-2">{new URL(p.url).hostname}{new URL(p.url).pathname}</a></span>
              ))}</div>
            )}
            <div className="num">{report.created_at.slice(0, 16).replace("T", " ")} · {Math.round(report.seconds)} s · {report.tokens.toLocaleString("en-IN")} tokens · {report.models.join(", ")}</div>
          </footer>
        </div>
      )}
    </section>
  );
}

function Items({ title, items, label, href, copy }: {
  title: string;
  items: DeepDiveItem[];
  label: (item: DeepDiveItem) => string;
  href?: (item: DeepDiveItem) => string | undefined;
  copy?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="label">{title}</div>
      <ul className="mt-1.5 divide-y divide-rule border-y border-rule">
        {items.map((item, i) => {
          const link = href?.(item);
          return (
            <li key={i} className="py-2.5">
              <div className="flex items-start justify-between gap-3">
                <span className="leading-snug">{item.text}</span>
                {copy && <CopyButton text={item.text} />}
              </div>
              <blockquote className="mt-1 border-l-2 border-rule pl-2.5 text-[12.5px] leading-snug text-soft">
                “{item.quote}”{" "}
                <span className="text-faint">· {link ? <a href={link} target="_blank" rel="noopener" className="underline underline-offset-2">{label(item)}</a> : label(item)}</span>
              </blockquote>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => { void navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1200); }); }}
      className="shrink-0 text-[12px] text-soft hover:text-ink"
    >
      {done ? "Copied" : "Copy"}
    </button>
  );
}
