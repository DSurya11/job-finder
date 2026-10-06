import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { SPRING } from "./fx";
import { item, stagger } from "./Inspector";
import Description from "./Description";
import { fetchJob, setState, type Job } from "./api";
import { STATUS, TONE, expOf, payOf, timeAgo } from "./ui";

// Job details are cached so stepping back and forth is instant, and the row after
// the cursor is fetched ahead of time.
const cache = new Map<string, Promise<Job>>();
export function loadJob(id: string): Promise<Job> {
  let hit = cache.get(id);
  if (!hit) {
    hit = fetchJob(id);
    hit.catch(() => cache.delete(id));
    cache.set(id, hit);
    if (cache.size > 200) cache.delete(cache.keys().next().value!);
  }
  return hit;
}
export const forgetJobs = () => cache.clear();

function Fact({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-rule py-2.5">
      <dt className="label">{name}</dt>
      <dd className="mt-0.5 min-w-0 text-[14px] leading-snug">{children}</dd>
    </div>
  );
}

export default function Detail({ id, picked, onPick, onClose, onChanged }: {
  id: string; picked: boolean; onPick: () => void; onClose: () => void; onChanged: (job: Job) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    let live = true;
    setJob(null);
    loadJob(id).then((j) => { if (live) { setJob(j); setNotes(j.notes ?? ""); } });
    return () => { live = false; };
  }, [id]);

  if (!job) {
    return (
      <div className="space-y-2 p-5">
        <div className="placeholder h-5 w-3/4" /><div className="placeholder h-4 w-1/3" /><div className="placeholder mt-5 h-64" />
      </div>
    );
  }

  const mark = async (status: string) => {
    const next = job.status === status ? "" : status;
    await setState(job.id, { status: next, notes });
    const updated = { ...job, status: next || null };
    cache.set(job.id, Promise.resolve(updated));
    setJob(updated);
    onChanged(updated);
  };
  const saveNotes = async () => {
    if (notes === (job.notes ?? "")) return;
    await setState(job.id, { notes });
    const updated = { ...job, notes, status: job.status ?? "saved" };
    cache.set(job.id, Promise.resolve(updated));
    setJob(updated);
    onChanged(updated);
  };

  const pay = payOf(job);
  const estimated = job.salary_max_lpa == null && job.est_max_lpa != null;
  return (
    <motion.article key={job.id} variants={stagger} initial="hidden" animate="show" className="thin h-full overflow-y-auto">
      <motion.header variants={item} className="border-b border-rule px-8 pb-5 pt-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[14px] font-medium text-soft">{job.company}</div>
            <h2 className="mt-1 text-[26px] font-semibold leading-tight tracking-[-0.01em]">{job.title}</h2>
          </div>
          <button onClick={onClose} className="shrink-0 text-[12px] text-soft hover:text-ink" title="Close">Close <kbd>esc</kbd></button>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <motion.a href={job.apply_url} target="_blank" rel="noopener" whileTap={{ scale: 0.96 }} transition={SPRING}
            className="flex h-9 items-center rounded-[4px] bg-mark px-5 text-[14px] font-semibold text-sheet hover:opacity-90">
            Apply
          </motion.a>
          {Object.entries(STATUS).map(([key, s]) => (
            <motion.button
              key={key} onClick={() => mark(key)} whileTap={{ scale: 0.95 }} transition={SPRING}
              className={`relative h-9 rounded-[4px] border px-3 text-[13px] transition-colors ${
                job.status === key ? "border-ink text-paper" : "border-rule text-soft hover:text-ink"
              }`}
            >
              {job.status === key && <motion.span layoutId="status-pill" className="absolute inset-0 rounded-[2px] bg-ink" transition={SPRING} />}
              <span className="relative">{key === "saved" ? "Shortlist" : s.label}</span>
            </motion.button>
          ))}
          <label className="ml-1 flex cursor-pointer items-center gap-1.5 text-[13px] text-soft">
            <input type="checkbox" checked={picked} onChange={onPick} className="size-3" /> Claude prompt
          </label>
        </div>
      </motion.header>

      {/* Wide: the description reads on the left, the facts stay in view on the right. */}
      <div className="grid gap-x-10 gap-y-6 px-8 py-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="order-2 min-w-0 lg:order-1">
          <motion.div variants={item} className="label mb-2">Description</motion.div>
          {job.description ? (
            <motion.div variants={item}><Description text={job.description} /></motion.div>
          ) : (
            <motion.p variants={item} className="text-[15px] text-soft">This source does not include the description. Open the posting to read it.</motion.p>
          )}
        </div>
        <aside className="order-1 lg:sticky lg:top-0 lg:order-2 lg:self-start">
          <motion.dl variants={item} className="border-t border-rule">
          <Fact name="Fit">
            <span className="num text-[17px] font-medium">{Math.round(job.score)}</span><span className="text-faint"> / 100</span>
            {job.score_reasons.length > 0 && <span className="mt-1 block text-[12.5px] leading-snug text-soft">{job.score_reasons.join(" · ")}</span>}
          </Fact>
          <Fact name="Pay">
            <span className={`num text-[17px] font-medium ${TONE[pay.tone]}`}>{pay.text === "—" ? "Not stated" : pay.text}</span>
            {estimated && (
              <span className="mt-1 block text-[12.5px] leading-snug text-soft">
                {job.est_source === "ambitionbox" || job.est_source === "market" ? (
                  <>{job.est_note} Not exact: the posting does not state pay.{" "}
                    {job.est_url && <a href={job.est_url} target="_blank" rel="noopener" className="underline underline-offset-2">Source</a>}</>
                ) : job.est_source === "claude"
                  ? "Estimate by Claude for this role and level at this company. Not exact: the posting does not state pay."
                  : "Rough guess from the company's general pay tier, the same for every role at this level. Not exact, and not from the posting."}
                {job.est_source === "claude" && job.brain_note && <span className="block">{job.brain_note}</span>}
              </span>
            )}
            {pay.text === "—" && <span className="block text-[12px] text-soft">Not in the posting, and nothing to estimate from.</span>}
          </Fact>
          <Fact name="Location">{job.location || "—"}</Fact>
          {job.others && job.others.length > 0 && (
            <Fact name="Also open">
              <span className="text-soft">{job.others.length} more posting{job.others.length > 1 ? "s" : ""} with this title: </span>
              {job.others.slice(0, 12).map((o, i) => (
                <span key={o.id}>{i > 0 && ", "}<a href={o.apply_url} target="_blank" rel="noopener" className="underline underline-offset-2">{o.location || "posting"}</a></span>
              ))}
            </Fact>
          )}
          <Fact name="Level">{job.level} · {job.role} · {job.employment_type}</Fact>
          <Fact name="Experience">{job.exp_min == null ? "Not stated" : expOf(job)}</Fact>
          <Fact name="Posted">{timeAgo(job.posted_at || job.first_seen) || "—"}{job.posted_at ? "" : " (first seen)"} · {job.source}</Fact>
          </motion.dl>
          <motion.textarea variants={item}
            value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes} placeholder="Notes"
            className="mt-4 h-24 w-full resize-y rounded-[4px] border border-rule bg-transparent p-2.5 text-[14px] outline-none placeholder:text-faint focus:border-soft"
          />
        </aside>
      </div>
    </motion.article>
  );
}
