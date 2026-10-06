import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { NumberTicker, SlidingHighlight, SPRING } from "./fx";
import {
  buildPrompt, emptyFilters, fetchFacets, fetchJobs, fetchProgress, setState, startRefresh,
  type Facets, type Filters, type Job, type Progress,
} from "./api";
import FilterBar from "./Filters";
import { JobRows, TableHead } from "./JobTable";
import Detail, { forgetJobs, loadJob } from "./Detail";
import Inspector from "./Inspector";
import { CoverageView } from "./Views";

const PAGE_SIZES = [25, 50, 100, 200];
const STATUS_VIEWS: [string, string][] = [
  ["saved", "Shortlisted"], ["applied", "Applied"], ["interview", "Interview"], ["offer", "Offer"], ["rejected", "Rejected"],
];
const KEYS: [string, string][] = [
  ["j / k", "next / previous"], ["o", "open the posting"], ["s", "shortlist"], ["a", "mark applied"],
  ["x", "dismiss"], ["c", "add to Claude prompt"], ["n / p", "next / previous page"], ["/", "search"], ["esc", "close card"],
];

export default function App() {
  const [view, setView] = useState("all");            // all | new | <status> | coverage
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [search, setSearch] = useState("");
  const [facets, setFacets] = useState<Facets | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(() => {
    const saved = Number(localStorage.getItem("rowsPerPage"));
    return PAGE_SIZES.includes(saved) ? saved : 50;
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [version, setVersion] = useState(0);
  const [showKeys, setShowKeys] = useState(false);
  const [setKey, setSetKey] = useState(0);            // bumps per new result set, replaying the row entrance
  const request = useRef(0);
  const table = useRef<HTMLElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);

  // Debounce typing so each keystroke is not a query.
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 250);
    return () => clearTimeout(t);
  }, [search]);

  // The left-rail view narrows the query on top of the top-bar filters. A status
  // view shows everything you tracked, regardless of pay or role filters.
  const query = useMemo<Filters>(() => {
    if (view === "new") return { ...filters, new_days: 1 };
    if (view === "all" || view === "coverage") return filters;
    return { ...emptyFilters, q: filters.q, sort: filters.sort, dir: filters.dir, tech: false, hide_bad: false, status: [view] };
  }, [filters, view]);

  const load = useCallback(async (f: Filters, p: number, perPage: number) => {
    const mine = ++request.current;
    setLoading(true);
    try {
      const res = await fetchJobs(f, p, perPage);
      if (mine !== request.current) return;   // a newer query superseded this one
      setJobs(res.jobs);
      setTotal(res.total);
      setSetKey((k) => k + 1);
      // A new page or result set: start at the top, and close the card if its job is gone.
      table.current?.scrollTo({ top: 0 });
      setOpenId((id) => (id && res.jobs.some((j) => j.id === id) ? id : null));
      setError("");
    } catch (e) {
      if (mine === request.current) setError(`Could not load jobs (${(e as Error).message}). Is the server running?`);
    } finally {
      if (mine === request.current) setLoading(false);
    }
  }, []);

  // A changed query or page size goes back to page 1; paging keeps the query.
  useEffect(() => { setPage(1); }, [query, size, view]);
  useEffect(() => { if (view !== "coverage") load(query, page, size); }, [query, version, view, page, size, load]);
  const pages = Math.max(1, Math.ceil(total / size));
  const goTo = useCallback((p: number) => setPage(Math.min(Math.max(1, p), Math.max(1, Math.ceil(total / size)))), [total, size]);
  const changeSize = (n: number) => { localStorage.setItem("rowsPerPage", String(n)); setSize(n); };
  // Menu counts follow the filters in force, so they are refetched with the query.
  const loadFacets = useCallback(() => { fetchFacets(filters).then(setFacets).catch(() => undefined); }, [filters]);
  useEffect(loadFacets, [version, loadFacets]);
  useEffect(forgetJobs, [version]);                   // a refresh may have changed any job

  // Warm the detail cache for the rows either side of the cursor.
  useEffect(() => {
    const at = jobs.findIndex((j) => j.id === openId);
    if (at < 0) return;
    for (const near of [jobs[at + 1], jobs[at - 1]]) if (near) loadJob(near.id).catch(() => undefined);
  }, [openId, jobs]);
  const open = useCallback((id: string) => setOpenId(id), []);

  // Poll while a refresh is running, then reload everything once it ends.
  useEffect(() => {
    let wasRunning = false;
    const tick = async () => {
      try {
        const p = await fetchProgress();
        setProgress(p);
        if (wasRunning && !p.running) setVersion((v) => v + 1);
        wasRunning = p.running;
      } catch { /* server not up yet */ }
    };
    tick();
    const timer = setInterval(tick, 2000);
    return () => clearInterval(timer);
  }, []);

  // In a status view (Shortlisted, Applied, …) a job leaves the list as soon as
  // its status stops matching the view.
  const leaves = useCallback(
    (status: string | null) => !["all", "new", "coverage"].includes(view) && status !== view, [view]);
  const mark = useCallback(async (job: Job, status: string) => {
    const next = job.status === status ? "" : status;
    await setState(job.id, { status: next });
    if (next === "hidden" || leaves(next || null)) {
      setJobs((list) => list.filter((j) => j.id !== job.id));
      setTotal((t) => t - 1);
    } else {
      setJobs((list) => list.map((j) => (j.id === job.id ? { ...j, status: next || null } : j)));
    }
    loadFacets();
  }, [loadFacets, leaves]);
  const togglePick = useCallback(
    (id: string) => setPicked((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id])), [],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Only text fields swallow keys. A checkbox or menu button keeps focus after a
      // click, and treating that as typing made the shortcuts stop working.
      const el = e.target as HTMLInputElement;
      const typing = el.tagName === "TEXTAREA" || el.tagName === "SELECT"
        || (el.tagName === "INPUT" && !["checkbox", "radio", "button"].includes(el.type));
      if (e.key === "Escape") {
        if (typing) el.blur();
        else if (showKeys) setShowKeys(false);
        else setOpenId(null);
        return;
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); searchBox.current?.focus(); return; }
      if (e.key === "?") { setShowKeys((v) => !v); return; }
      if (view !== "coverage" && !openId && e.key === "n") { goTo(page + 1); return; }
      if (view !== "coverage" && !openId && e.key === "p") { goTo(page - 1); return; }
      if (view === "coverage" || !jobs.length) return;
      const at = jobs.findIndex((j) => j.id === openId);
      const job = jobs[at];
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setOpenId(jobs[Math.min(at + 1, jobs.length - 1)].id); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setOpenId(jobs[Math.max(at - 1, 0)].id); }
      else if (!job) return;
      else if (e.key === "o" || e.key === "Enter") window.open(job.apply_url, "_blank", "noopener");
      else if (e.key === "s") mark(job, "saved");
      else if (e.key === "a") mark(job, "applied");
      else if (e.key === "x") { setOpenId(jobs[at + 1]?.id ?? jobs[at - 1]?.id ?? null); mark(job, "hidden"); }
      else if (e.key === "c") togglePick(job.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [jobs, openId, view, showKeys, mark, togglePick, goTo, page]);

  const copyPrompt = async () => {
    const { prompt } = await buildPrompt(picked);
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const running = progress?.running ?? false;
  const counts: Record<string, number | undefined> = {
    all: facets?.rows.all, new: facets?.rows.new, ...(facets?.tracker ?? {}),
  };
  const railItem = (key: string, label: string) => (
    <button
      key={key} onClick={() => { setView(key); setOpenId(null); }}
      className={`relative flex h-7 w-full items-center justify-between rounded-[3px] px-2 text-left text-[12.5px] transition-colors ${
        view === key ? "font-medium text-ink" : "text-soft hover:text-ink"
      }`}
    >
      <SlidingHighlight active={view === key} id="rail" className="rounded-[3px] bg-tint" />
      <span className="relative">{label}</span>
      {counts[key] ? <NumberTicker value={counts[key]!} className="num relative text-[11px] text-faint" /> : null}
    </button>
  );

  return (
    <MotionConfig reducedMotion="user">
    <div className="flex h-full">
      <nav className="hidden w-[168px] shrink-0 flex-col border-r border-rule p-2 md:flex">
        <div className="px-2 pb-3 pt-1.5 text-[13px] font-semibold">Job Finder</div>
        {railItem("all", "All")}
        {railItem("new", "New today")}
        <div className="my-2 border-t border-rule" />
        {STATUS_VIEWS.map(([key, label]) => railItem(key, label))}
        <div className="my-2 border-t border-rule" />
        {railItem("coverage", "Coverage")}
        <div className="mt-auto space-y-1 px-2 pb-1 text-[12px] text-soft">
          <button
            disabled={running} onClick={() => startRefresh().then(() => setProgress({ running: true, done: 0, total: 0, current: "" }))}
            className="block text-left hover:text-ink disabled:text-faint"
          >
            {running ? <span className="num">Fetching {progress?.done ?? 0}/{progress?.total ?? 0}</span> : "Refresh jobs"}
          </button>
          <button onClick={() => setShowKeys(true)} className="block hover:text-ink">Shortcuts <kbd>?</kbd></button>
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-rule px-3 py-1.5">
          <select value={view} onChange={(e) => setView(e.target.value)} className="h-7 rounded-[3px] border border-rule bg-paper px-1 text-[12.5px] md:hidden">
            <option value="all">All</option><option value="new">New today</option>
            {STATUS_VIEWS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            <option value="coverage">Coverage</option>
          </select>
          <div className="relative w-full max-w-[300px] flex-1">
            <input
              ref={searchBox} value={search} onChange={(e) => { setSearch(e.target.value); if (view === "coverage") setView("all"); }}
              placeholder="Search"
              className="h-7 w-full rounded-[3px] border border-rule bg-sheet pl-2 pr-7 text-[12.5px] outline-none placeholder:text-faint focus:border-soft"
            />
            <kbd className="absolute right-1.5 top-[6px]">/</kbd>
          </div>
          {(view === "all" || view === "new") && <FilterBar facets={facets} filters={filters} onChange={setFilters} />}
          <p className="ml-auto whitespace-nowrap text-[12px] text-soft">
            {view !== "coverage" && <><NumberTicker value={total} className="num text-ink" /> shown · </>}
            <NumberTicker value={facets?.rows.new ?? 0} className="num text-ink" /> new since yesterday
          </p>
        </header>

        <div className={loading && view !== "coverage" ? "loading-bar" : "h-[2px]"} />
        {view === "coverage" ? (
          <main className="thin min-h-0 flex-1 overflow-y-auto"><CoverageView version={version} /></main>
        ) : (
          <main className="flex min-h-0 flex-1">
            <div className="flex min-w-0 flex-1 flex-col">
            <section ref={table} className="thin @container min-h-0 flex-1 overflow-y-auto" role="table">
              <TableHead sort={filters.sort} dir={filters.dir} onSort={(key, dir) => setFilters({ ...filters, sort: key, dir })} />
              {error && <p className="border-b border-rule px-3 py-2 text-bad">{error}</p>}
              {loading && !jobs.length && Array.from({ length: 14 }, (_, i) => <div key={i} className="placeholder mx-3 my-1.5 h-6" />)}
              {!loading && !error && !jobs.length && (
                <p className="px-3 py-3 text-soft">
                  {view !== "all" && view !== "new" ? "Nothing here yet."
                    : facets?.totals.jobs ? "No jobs match these filters." : "No jobs yet. Use Refresh jobs to fetch them."}
                </p>
              )}
              <JobRows jobs={jobs} setKey={setKey} openId={openId} picked={picked} onOpen={open} />
            </section>
            <footer className="flex h-10 shrink-0 items-center gap-4 border-t border-rule px-3 text-[12.5px] text-soft">
              <label className="flex items-center gap-2">
                Rows per page
                <select
                  value={size} onChange={(e) => changeSize(Number(e.target.value))}
                  className="num h-7 rounded-[3px] border border-rule bg-paper px-1.5 text-[12px] text-ink outline-none"
                >
                  {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <span className="num">
                {total === 0 ? "0" : `${((page - 1) * size + 1).toLocaleString("en-IN")}–${Math.min(page * size, total).toLocaleString("en-IN")}`} of {total.toLocaleString("en-IN")}
              </span>
              <div className="ml-auto flex items-center gap-1.5">
                <button onClick={() => goTo(1)} disabled={page <= 1 || loading} title="First page"
                  className="h-7 rounded-[3px] border border-rule px-2 hover:text-ink disabled:opacity-35">First</button>
                <button onClick={() => goTo(page - 1)} disabled={page <= 1 || loading} title="Previous page (p)"
                  className="h-7 rounded-[3px] border border-rule px-2.5 hover:text-ink disabled:opacity-35">Previous</button>
                <span className="num px-2">Page <span className="text-ink">{page.toLocaleString("en-IN")}</span> of {pages.toLocaleString("en-IN")}</span>
                <button onClick={() => goTo(page + 1)} disabled={page >= pages || loading} title="Next page (n)"
                  className="h-7 rounded-[3px] border border-rule px-2.5 hover:text-ink disabled:opacity-35">Next</button>
                <button onClick={() => goTo(pages)} disabled={page >= pages || loading} title="Last page"
                  className="h-7 rounded-[3px] border border-rule px-2 hover:text-ink disabled:opacity-35">Last</button>
              </div>
            </footer>
            </div>
          </main>
        )}
      </div>

      <AnimatePresence>
        {openId && view !== "coverage" && (
          <Inspector key="inspector" id={openId} onClose={() => setOpenId(null)}>
            <Detail
              id={openId} picked={picked.includes(openId)} onPick={() => togglePick(openId)} onClose={() => setOpenId(null)}
              onChanged={(job) => {
                if (leaves(job.status)) {
                  setJobs((list) => list.filter((j) => j.id !== job.id));
                  setTotal((t) => t - 1);
                  setOpenId(null);
                } else {
                  setJobs((list) => list.map((j) => (j.id === job.id ? { ...j, status: job.status } : j)));
                }
                loadFacets();
              }}
            />
          </Inspector>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {picked.length > 0 && (
          <motion.div
            initial={{ y: 28, opacity: 0, x: "-50%" }} animate={{ y: 0, opacity: 1, x: "-50%" }}
            exit={{ y: 20, opacity: 0, x: "-50%", transition: { duration: 0.12 } }} transition={SPRING}
            className="fixed bottom-3 left-1/2 z-[60] flex items-center gap-3 rounded-[3px] border border-soft bg-sheet px-3 py-1.5 text-[12.5px]"
          >
            <span><NumberTicker value={picked.length} className="num" /> selected</span>
            <motion.button whileTap={{ scale: 0.96 }} onClick={copyPrompt} className="h-6 rounded-[3px] bg-mark px-2 font-medium text-sheet">
              {copied ? "Copied. Paste into Claude" : "Copy Claude prompt"}
            </motion.button>
            <button onClick={() => setPicked([])} className="text-soft underline underline-offset-2 hover:text-ink">Clear</button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showKeys && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}
            className="fixed inset-0 z-[70] grid place-items-center bg-black/25" onClick={() => setShowKeys(false)}
          >
            <motion.div
              initial={{ scale: 0.96, y: 6 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, y: 4 }} transition={SPRING}
              className="rounded-[4px] border border-rule bg-sheet p-4" onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-2 text-[13px] font-semibold">Shortcuts</div>
              {KEYS.map(([key, what]) => (
                <div key={key} className="flex gap-4 py-0.5 text-[12.5px]"><span className="w-12"><kbd>{key}</kbd></span><span className="text-soft">{what}</span></div>
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </MotionConfig>
  );
}
