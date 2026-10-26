import { useEffect, useState } from "react";
import { decideFix, fetchCoverage, fetchFixes, type Coverage, type FixProposal } from "./api";

const MEANING: Record<string, string> = {
  ok: "fetched", empty: "listed nothing", dropped: "sharp drop", failed: "failed", manual: "no scraper",
};
const STATUS_TONE: Record<string, string> = {
  ok: "text-soft", empty: "text-warn", dropped: "text-warn", failed: "text-bad", manual: "text-faint",
};

export function CoverageView({ version }: { version: number }) {
  const [data, setData] = useState<Coverage | null>(null);
  const [only, setOnly] = useState<string | null>(null);
  useEffect(() => { fetchCoverage().then(setData); }, [version]);
  if (!data) return <div className="placeholder m-4 h-40" />;
  if (!data.run) return <p className="p-4 text-soft">No run yet.</p>;
  const rows = data.companies.filter((c) => !only || c.status === only);
  return (
    <div>
      <ProposedFixes version={version} />
      <div className="flex flex-wrap gap-x-5 gap-y-1 border-b border-rule px-3 py-2 text-[12.5px]">
        {Object.keys(MEANING).map((status) => (
          <button key={status} onClick={() => setOnly(only === status ? null : status)}
            className={only === status ? "text-ink underline underline-offset-4" : "text-soft hover:text-ink"}>
            <span className="num">{data.summary[status] ?? 0}</span> {MEANING[status]}
          </button>
        ))}
      </div>
      <table className="w-full text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-rule">
            {["Company", "Source", "Status", "India jobs", "Last run", "All postings", "Note"].map((h, i) => (
              <th key={h} className={`label h-7 px-3 font-medium ${i >= 3 && i <= 5 ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.company} className="h-8 border-b border-rule hover:bg-sheet">
              <td className="px-3 font-medium">{c.company}</td>
              <td className="px-3 text-soft">{c.ats}</td>
              <td className={`px-3 ${STATUS_TONE[c.status]}`}>{c.status}</td>
              <td className="num px-3 text-right">{c.india.toLocaleString("en-IN")}</td>
              <td className="num px-3 text-right text-faint">{c.previous?.toLocaleString("en-IN") ?? "—"}</td>
              <td className="num px-3 text-right text-faint">{c.raw.toLocaleString("en-IN")}</td>
              <td className="max-w-[260px] truncate px-3 text-soft">{c.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Boards the repair agent found for broken sources. Code already proved each has India jobs;
 *  nothing changes in companies.yaml until Approve. */
function ProposedFixes({ version }: { version: number }) {
  const [fixes, setFixes] = useState<FixProposal[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => { fetchFixes().then((r) => setFixes(r.fixes.filter((f) => f.status === "pending"))).catch(() => undefined); }, [version]);
  if (fixes.length === 0) return null;
  const board = (b: Record<string, string>) => b.ats === "workday" ? `workday ${b.tenant}/${b.site}` : `${b.ats} ${b.slug ?? ""}`;
  async function decide(f: FixProposal, decision: "approve" | "reject") {
    setBusy(f.id); setNote("");
    try {
      await decideFix(f.id, decision);
      setFixes((all) => all.filter((x) => x.id !== f.id));
      setNote(decision === "approve" ? `${f.company}: applied and fetched.` : `${f.company}: rejected.`);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not save the decision.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="border-b border-rule">
      <div className="flex items-baseline justify-between px-3 pb-1 pt-3">
        <div className="label">Proposed fixes · found by the repair agent, checked by code, applied only when you approve</div>
        {note && <span className="text-[12px] text-soft">{note}</span>}
      </div>
      <table className="w-full text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-rule">
            {["Company", "Was", "Proposed", "India jobs", "Sample titles", "Why", ""].map((h, i) => (
              <th key={i} className={`label h-7 px-3 font-medium ${i === 3 ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fixes.map((f) => (
            <tr key={f.id} className="border-b border-rule align-top">
              <td className="px-3 py-2 font-medium">{f.company}</td>
              <td className="px-3 py-2 text-soft">{board(f.current)} <span className="text-faint">({f.last_fetch})</span></td>
              <td className="px-3 py-2">{board(f.proposed)}</td>
              <td className="num px-3 py-2 text-right">{f.india_jobs.toLocaleString("en-IN")}</td>
              <td className="max-w-[240px] px-3 py-2 text-soft">{f.sample_titles.slice(0, 3).join(" · ")}</td>
              <td className="max-w-[260px] px-3 py-2 text-soft">{f.evidence}</td>
              <td className="whitespace-nowrap px-3 py-2 text-right">
                <button disabled={busy === f.id} onClick={() => decide(f, "approve")}
                  className="h-7 rounded-[4px] bg-mark px-2.5 text-sheet hover:opacity-90 disabled:opacity-50">Approve</button>{" "}
                <button disabled={busy === f.id} onClick={() => decide(f, "reject")}
                  className="h-7 rounded-[4px] border border-rule px-2.5 text-soft hover:text-ink disabled:opacity-50">Reject</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

