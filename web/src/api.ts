export type Job = {
  id: string;
  company: string;
  title: string;
  location: string;
  cities: string[];
  is_remote: boolean;
  scope: string;
  employment_type: string;
  level: string;
  role: string;
  is_tech: boolean;
  exp_min: number | null;
  exp_max: number | null;
  salary_min_lpa: number | null;
  salary_max_lpa: number | null;
  salary_text: string;
  apply_url: string;
  source: string;
  posted_at: string;
  first_seen: string;
  score: number;
  score_reasons: string[];
  pay_verdict: string;
  est_min_lpa: number | null;
  est_max_lpa: number | null;
  est_source: "band" | "ambitionbox" | "market" | null;
  est_note: string | null;
  est_url: string | null;
  openings?: number;
  /** false once the posting is gone; only your status tabs still show it. */
  is_active?: boolean;
  closed_at?: string | null;
  others?: { id: string; location: string; apply_url: string }[];
  snippet?: string;
  description?: string;
  departments?: string;
  status: string | null;
  notes?: string | null;
};

export type Facet = { value: string; count: number };
export type Facets = {
  totals: { jobs: number; companies: number; tech: number; with_salary: number; with_description: number; new_today: number };
  tracker: Record<string, number>;
  rows: { all: number; new: number };
  role: Facet[]; level: Facet[]; type: Facet[]; company: Facet[]; source: Facet[]; city: Facet[]; pay: Facet[];
};

export type CoverageRow = {
  company: string; ats: string; status: string; raw: number; india: number;
  previous: number | null; error: string; seconds: number;
};
export type Coverage = {
  run: { started: string; finished: string | null; raw_total: number; india_total: number; new_jobs: number; closed_jobs: number } | null;
  companies: CoverageRow[];
  summary: Record<string, number>;
};

export type Progress = { running: boolean; done: number; total: number; current: string };

export type Filters = {
  q: string; role: string[]; level: string[]; type: string[]; city: string[]; company: string[];
  source: string[]; pay: string[]; status: string[]; remote: boolean; tech: boolean; has_salary: boolean; hide_bad: boolean; has_description: boolean;
  min_score: number | null;
  salary_min: number | null; exp_max: number | null; new_days: number | null; posted_days: number | null; sort: string; dir: "asc" | "desc";
};

export const emptyFilters: Filters = {
  q: "", role: [], level: [], type: [], city: [], company: [], source: [], pay: [], status: [],
  remote: false, tech: true, has_salary: false, hide_bad: true, has_description: false,
  min_score: null, salary_min: null, exp_max: null,
  new_days: null, posted_days: null, sort: "score", dir: "desc",
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

function toParams(f: Filters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set("q", f.q.trim());
  for (const key of ["role", "level", "type", "city", "company", "source", "pay", "status"] as const) {
    if (f[key].length) p.set(key, f[key].join(","));
  }
  if (f.remote) p.set("remote", "true");
  if (f.tech) p.set("tech", "true");
  if (f.has_salary) p.set("has_salary", "true");
  if (f.hide_bad) p.set("hide_bad", "true");
  if (f.has_description) p.set("has_description", "true");
  if (f.min_score != null) p.set("min_score", String(f.min_score));
  if (f.salary_min != null) p.set("salary_min", String(f.salary_min));
  if (f.exp_max != null) p.set("exp_max", String(f.exp_max));
  if (f.new_days != null) p.set("new_days", String(f.new_days));
  if (f.posted_days != null) p.set("posted_days", String(f.posted_days));
  return p;
}

export function fetchJobs(f: Filters, page: number, size = 30) {
  const p = toParams(f);
  p.set("page", String(page));
  p.set("size", String(size));
  p.set("sort", f.sort);
  p.set("dir", f.dir);
  return json<{ total: number; jobs: Job[] }>(`/api/jobs?${p}`);
}

export const fetchJob = (id: string) => json<Job>(`/api/jobs/${id}`);
export const fetchFacets = (f: Filters) => json<Facets>(`/api/facets?${toParams(f)}`);
export const fetchCoverage = () => json<Coverage>("/api/coverage");
export const fetchProgress = () => json<Progress>("/api/refresh");
export const startRefresh = () => json<{ started: boolean }>("/api/refresh", { method: "POST" });

export const setState = (id: string, body: { status?: string; notes?: string }) =>
  json<{ ok: boolean }>(`/api/jobs/${id}/state`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });

export const buildPrompt = (job_ids: string[]) =>
  json<{ prompt: string }>("/api/prompt", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job_ids }),
  });

export type PayFloors = { min_lpa: number; target_lpa: number };
export const fetchPayFloors = () => json<PayFloors>("/api/settings/pay");

/** Saves the floors to user_profile.yaml; the server then re-scores every job in the background. */
export async function savePayFloors(floors: PayFloors): Promise<PayFloors & { rescoring: boolean }> {
  const res = await fetch("/api/settings/pay", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(floors),
  });
  const body = await res.json().catch(() => ({}));
  // The server says why it refused ("need 0 < minimum <= target"), so show that, not "400".
  if (!res.ok) throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  return body;
}

export type AskStep =
  | { kind: "model"; step: number; model: string; tokens_in: number | null; tokens_out: number | null; seconds: number; finish_reason: string; text: string }
  | { kind: "tool"; step: number; tool: string; arguments: string; failed: boolean; result: string }
  | { kind: "answer"; step: number; job_ids: string[] }
  | { kind: "error"; step: number; error: string };
export type AskResult = {
  answer: string; stopped: "answered" | "step_limit" | "token_budget" | "error";
  /** From the agent's last search, counted by the database: not the model's claim. */
  total_matching: number | null;
  /** That search's filters, to list every match; null when the agent never searched. */
  search: Record<string, unknown> | null;
  steps: AskStep[]; tokens_in: number; tokens_out: number; seconds: number; jobs: Job[];
};

/** Asks the agent; a few seconds. The jobs are database rows, in the agent's order. */
export async function askJobs(question: string): Promise<AskResult> {
  const res = await fetch("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  return body;
}

/** Every job matching the agent's last search, paged, without the groups of its picks. */
export async function fetchAskMatches(search: Record<string, unknown>, exclude: string[], page: number,
                                      size: number, sort: string, dir: "asc" | "desc") {
  const res = await fetch("/api/ask/matches", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ search, exclude, page, size, sort, dir }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  return body as { total: number; page: number; size: number; jobs: Job[] };
}
