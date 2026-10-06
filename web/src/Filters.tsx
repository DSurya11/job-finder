import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { EASE, NumberTicker } from "./fx";
import { emptyFilters, type Facet, type Facets, type Filters } from "./api";

/** A top-bar button that opens a small panel beneath it. */
function Menu({ label, count, align = "left", children }: {
  label: string; count?: number; align?: "left" | "right"; children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    // Escape closes the menu only; it must not also close the detail panel.
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex h-7 items-center gap-1.5 rounded-[3px] border px-2 text-[12.5px] ${
          count ? "border-mark text-ink" : "border-rule text-soft hover:text-ink"
        } ${open ? "bg-tint" : ""}`}
      >
        {label}
        {count ? <span className="num text-[11px] text-mark">{count}</span> : null}
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.14 }} className="text-[9px] text-faint">▾</motion.span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -3, scale: 0.98, transition: { duration: 0.08 } }}
            transition={{ duration: 0.14, ease: EASE }}
            style={{ transformOrigin: align === "right" ? "top right" : "top left" }}
            className={`thin absolute top-8 z-30 max-h-[70vh] w-60 overflow-y-auto rounded-[3px] border border-rule bg-sheet p-2 ${align === "right" ? "right-0" : "left-0"}`}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Options({ options, selected, onChange, labels, searchable }: {
  options: Facet[]; selected: string[]; onChange: (next: string[]) => void;
  labels?: Record<string, string>; searchable?: boolean;
}) {
  const [query, setQuery] = useState("");
  // A ticked option stays listed even when the other filters leave it with no rows.
  const all = [...options, ...selected.filter((v) => !options.some((o) => o.value === v)).map((v) => ({ value: v, count: 0 }))];
  const shown = all.filter((o) => o.value.toLowerCase().includes(query.toLowerCase())).slice(0, 120);
  const toggle = (v: string) => onChange(selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v]);
  return (
    <>
      {searchable && (
        <input
          autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find"
          className="mb-1 w-full border-b border-rule bg-transparent px-1 py-1 text-[12.5px] outline-none placeholder:text-faint"
        />
      )}
      {shown.map((o) => (
        <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded-[2px] px-1 py-1 hover:bg-tint">
          <input type="checkbox" checked={selected.includes(o.value)} onChange={() => toggle(o.value)} className="size-3" />
          <span className="flex-1 truncate text-[12.5px]">{labels?.[o.value] ?? o.value}</span>
          <NumberTicker value={o.count} className="num text-[11px] text-faint" />
        </label>
      ))}
      {selected.length > 0 && (
        <button onClick={() => onChange([])} className="mt-1 px-1 text-[12px] text-soft underline underline-offset-2">Clear</button>
      )}
    </>
  );
}

function Check({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-[2px] px-1 py-1 hover:bg-tint">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} className="size-3" />
      <span className="text-[12.5px]">{label}</span>
    </label>
  );
}

function Steps<T extends number | null>({ title, steps, value, onChange, label }: {
  title: string; steps: T[]; value: T; onChange: (v: T) => void; label: (v: T) => string;
}) {
  return (
    <div className="px-1 py-1.5">
      <div className="label mb-1">{title}</div>
      <div className="flex flex-wrap gap-1">
        {steps.map((s) => (
          <button
            key={String(s)} onClick={() => onChange(s)}
            className={`num rounded-[3px] border px-1.5 py-0.5 text-[11.5px] ${
              value === s ? "border-mark bg-mark text-sheet" : "border-rule text-soft hover:text-ink"
            }`}
          >
            {label(s)}
          </button>
        ))}
      </div>
    </div>
  );
}

const LEVEL_ORDER = ["Intern", "Entry", "Mid", "Senior", "Staff+", "Manager", "Unspecified"];
const PAY_LABEL: Record<string, string> = {
  target: "Meets target", ok: "Meets minimum", estimated: "Estimate meets minimum",
  unknown: "Not stated", low: "Below minimum", unpaid: "Unpaid", suspicious: "Looks fake",
};
const PAY_ORDER = Object.keys(PAY_LABEL);
const byOrder = (order: string[]) => (a: Facet, b: Facet) => order.indexOf(a.value) - order.indexOf(b.value);
const NEW_STEPS: [number | null, string][] = [[null, "Any"], [1, "24h"], [3, "3d"], [7, "7d"]];
const POSTED: [number | null, string][] = [
  [null, "Any time"], [1, "Last 24 hours"], [3, "Last 3 days"], [7, "Last 7 days"],
  [14, "Last 14 days"], [30, "Last 30 days"], [90, "Last 3 months"],
];

export default function FilterBar({ facets, filters, onChange }: {
  facets: Facets | null; filters: Filters; onChange: (f: Filters) => void;
}) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => onChange({ ...filters, [key]: value });
  if (!facets) return null;
  const more =
    filters.source.length + filters.type.length + filters.company.length +
    Number(filters.remote) + Number(filters.has_salary) + Number(filters.has_description) +
    Number(filters.exp_max != null) + Number(filters.min_score != null) + Number(filters.new_days != null) +
    Number(!filters.tech);
  const payCount = filters.pay.length + Number(filters.salary_min != null) + Number(!filters.hide_bad);
  const changed = JSON.stringify({ ...filters, q: "", sort: "", dir: "", status: [] }) !== JSON.stringify({ ...emptyFilters, q: "", sort: "", dir: "", status: [] });
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Menu label="Level" count={filters.level.length}>
        <Options options={[...facets.level].sort(byOrder(LEVEL_ORDER))} selected={filters.level} onChange={(v) => set("level", v)} />
      </Menu>
      <Menu label="Role" count={filters.role.length}>
        <Options options={facets.role} selected={filters.role} onChange={(v) => set("role", v)} />
      </Menu>
      <Menu label="City" count={filters.city.length}>
        <Options options={facets.city} selected={filters.city} onChange={(v) => set("city", v)} searchable />
      </Menu>
      <Menu label="Pay" count={payCount}>
        <Check label="Hide low-pay, unpaid and fake" on={filters.hide_bad} onChange={(v) => set("hide_bad", v)} />
        <Steps title="Low end of pay at least (LPA)" steps={[null, 6, 9, 12, 15, 20, 30]} value={filters.salary_min}
          onChange={(v) => set("salary_min", v)} label={(v) => (v == null ? "Any" : `${v}`)} />
        <div className="label px-1 pb-0.5 pt-1.5">Pay check</div>
        <Options labels={PAY_LABEL} options={[...facets.pay].sort(byOrder(PAY_ORDER))} selected={filters.pay} onChange={(v) => set("pay", v)} />
      </Menu>
      <Menu label={filters.posted_days == null ? "Posted" : POSTED.find((p) => p[0] === filters.posted_days)![1]} count={filters.posted_days == null ? 0 : 1}>
        {POSTED.map(([days, label]) => (
          <label key={label} className="flex cursor-pointer items-center gap-2 rounded-[2px] px-1 py-1 hover:bg-tint">
            <input type="radio" name="posted" checked={filters.posted_days === days} onChange={() => set("posted_days", days)} className="size-3 accent-[var(--mark)]" />
            <span className="text-[12.5px]">{label}</span>
          </label>
        ))}
      </Menu>
      <Menu label="Company" count={filters.company.length}>
        <Options options={facets.company} selected={filters.company} onChange={(v) => set("company", v)} searchable />
      </Menu>
      <Menu label="More" count={more} align="right">
        <Check label="Tech roles only" on={filters.tech} onChange={(v) => set("tech", v)} />
        <Check label="Remote" on={filters.remote} onChange={(v) => set("remote", v)} />
        <Check label="Salary stated" on={filters.has_salary} onChange={(v) => set("has_salary", v)} />
        <Check label="Has description" on={filters.has_description} onChange={(v) => set("has_description", v)} />
        <Steps title="Experience asked" steps={[null, 0, 1, 2, 3, 5]} value={filters.exp_max}
          onChange={(v) => set("exp_max", v)} label={(v) => (v == null ? "Any" : v === 0 ? "Fresher" : `≤${v}y`)} />
        <Steps title="Fit at least" steps={[null, 50, 60, 70, 80]} value={filters.min_score}
          onChange={(v) => set("min_score", v)} label={(v) => (v == null ? "Any" : `${v}`)} />
        <Steps title="First seen within" steps={NEW_STEPS.map((s) => s[0])} value={filters.new_days}
          onChange={(v) => set("new_days", v)} label={(v) => NEW_STEPS.find((s) => s[0] === v)![1]} />
        <div className="label px-1 pb-0.5 pt-1.5">Source</div>
        <Options options={facets.source} selected={filters.source} onChange={(v) => set("source", v)} />
        <div className="label px-1 pb-0.5 pt-1.5">Type</div>
        <Options options={facets.type} selected={filters.type} onChange={(v) => set("type", v)} />
      </Menu>
      {changed && (
        <button
          onClick={() => onChange({ ...emptyFilters, q: filters.q, sort: filters.sort, dir: filters.dir, status: filters.status })}
          className="px-1 text-[12px] text-soft underline underline-offset-2 hover:text-ink"
        >
          Reset
        </button>
      )}
    </div>
  );
}
