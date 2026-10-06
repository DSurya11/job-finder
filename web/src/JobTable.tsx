import { memo, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { EASE, SPRING } from "./fx";
import type { Job } from "./api";
import { STATUS, TONE, payOf, placeOf, timeAgo } from "./ui";

// label, sort key, direction a first click gives, classes (columns drop out as the table narrows)
const COLUMNS: [string, string, "asc" | "desc", string][] = [
  ["Fit", "score", "desc", ""],
  ["Company", "company", "asc", ""],
  ["Title", "title", "asc", ""],
  ["Location", "location", "asc", "hidden @2xl:block"],
  ["Pay", "pay", "desc", ""],
  ["Posted", "posted", "desc", "text-right"],
  ["Source", "source", "asc", "hidden @4xl:block"],
  ["Status", "status", "asc", "hidden @xl:block"],
];
const GRID =
  "grid h-9 items-center gap-x-3 px-3 " +
  "grid-cols-[1.75rem_6.5rem_minmax(0,1fr)_7rem_2.75rem] " +
  "@xl:grid-cols-[1.75rem_8rem_minmax(0,1fr)_7.25rem_2.75rem_5rem] " +
  "@2xl:grid-cols-[1.75rem_8.5rem_minmax(0,1.5fr)_minmax(0,0.8fr)_7.25rem_2.75rem_5rem] " +
  "@4xl:grid-cols-[1.75rem_9.5rem_minmax(0,1.5fr)_minmax(0,0.8fr)_7.5rem_2.75rem_5.5rem_5.5rem]";

export function TableHead({ sort, dir, onSort }: {
  sort: string; dir: "asc" | "desc"; onSort: (key: string, dir: "asc" | "desc") => void;
}) {
  return (
    <div className={`${GRID} sticky top-0 z-10 !h-7 border-b border-rule bg-paper`}>
      {COLUMNS.map(([label, key, first, cls]) => {
        const active = sort === key;
        return (
          <div key={label} className={cls}>
            <button
              // A first click sorts the natural way for the column; clicking again reverses it.
              onClick={() => onSort(key, active ? (dir === "asc" ? "desc" : "asc") : first)}
              aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
              title={`Sort by ${label.toLowerCase()}`}
              className={`label group whitespace-nowrap hover:text-ink ${active ? "!text-ink" : ""}`}
            >
              {label}
              <span className={`ml-0.5 inline-block w-2 ${active ? "" : "opacity-0 group-hover:opacity-40"}`}>
                {active ? (dir === "asc" ? "↑" : "↓") : first === "asc" ? "↑" : "↓"}
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

const STAGGER = 16;     // only the first screenful animates in; the rest just appear

type RowProps = { job: Job; active: boolean; picked: boolean; index: number; onOpen: (id: string) => void };

/** Memoised: moving the cursor re-renders two rows, not the whole table. */
export const JobRow = memo(function JobRow({ job, active, picked, index, onOpen }: RowProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest" });
  }, [active]);
  const pay = payOf(job);
  const estimated = job.salary_max_lpa == null && job.est_max_lpa != null;
  const status = job.status ? STATUS[job.status] : null;
  const enters = index < STAGGER;
  return (
    <motion.div
      ref={ref} onClick={() => onOpen(job.id)} role="row" aria-selected={active} data-job={job.id}
      initial={enters ? { opacity: 0, y: 6, filter: "blur(3px)" } : false}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      exit={{ opacity: 0, x: -24, height: 0, transition: { duration: 0.18, ease: EASE } }}
      transition={{ duration: 0.26, ease: EASE, delay: enters ? index * 0.014 : 0 }}
      className={`${GRID} row relative cursor-pointer overflow-hidden border-b border-rule ${active ? "bg-tint" : "hover:bg-sheet"}`}
    >
      {active && <motion.span layoutId="cursor" className="absolute inset-y-0 left-0 w-[2px] bg-mark" transition={SPRING} />}
      <span className={`num text-[12.5px] ${job.score >= 70 ? "font-medium text-ink" : "text-faint"}`}>{Math.round(job.score)}</span>
      <span className="truncate text-[12.5px] text-soft">{job.company}</span>
      <span className="truncate font-medium">
        {picked && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={SPRING} className="mr-1.5 inline-block text-mark" title="Selected for the Claude prompt">+</motion.span>}
        {job.title}
        {(job.openings ?? 1) > 1 && <span className="num ml-1.5 text-[11px] font-normal text-faint">×{job.openings}</span>}
      </span>
      <span className="hidden truncate text-[12.5px] text-soft @2xl:block">{placeOf(job)}</span>
      <span className={`num truncate text-[11.5px] ${TONE[pay.tone]}`} title={estimated ? "Rough estimate. The posting does not state pay." : pay.text}>
        {pay.text}{estimated && <span className="text-faint"> {job.est_source === "band" ? "guess" : job.est_source === "market" ? "mkt" : "est"}</span>}
      </span>
      <span className="num text-right text-[11.5px] text-faint">{timeAgo(job.posted_at || job.first_seen)}</span>
      <span className="hidden truncate text-[12px] text-faint @4xl:block">{job.source}</span>
      <span className="hidden items-center gap-1.5 text-[12px] text-soft @xl:flex">
        {status ? (
          <motion.span key={job.status} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={SPRING} className="flex items-center gap-1.5">
            <motion.i initial={{ scale: 2.2 }} animate={{ scale: 1 }} transition={SPRING} className={`size-1.5 rounded-full ${status.dot}`} />{status.label}
          </motion.span>
        ) : <span className="text-faint">New</span>}
      </span>
    </motion.div>
  );
});

/** The rows of one result set. `setKey` changes when the query does, replaying the entrance. */
export function JobRows({ jobs, setKey, openId, picked, onOpen }: {
  jobs: Job[]; setKey: number; openId: string | null; picked: string[]; onOpen: (id: string) => void;
}) {
  return (
    <div key={setKey}>
      <AnimatePresence initial={false}>
        {jobs.map((job, i) => (
          <JobRow key={job.id} job={job} index={i} active={job.id === openId} picked={picked.includes(job.id)} onOpen={onOpen} />
        ))}
      </AnimatePresence>
    </div>
  );
}
