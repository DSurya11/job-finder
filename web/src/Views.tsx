import { useEffect, useState } from "react";
import { fetchCoverage, type Coverage } from "./api";

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
              <td className="num px-3 text-right text-faint">{c.previous ?? "—"}</td>
              <td className="num px-3 text-right text-faint">{c.raw.toLocaleString("en-IN")}</td>
              <td className="max-w-[260px] truncate px-3 text-soft">{c.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
