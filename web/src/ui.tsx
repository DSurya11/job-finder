import type { Job } from "./api";

export function timeAgo(iso: string): string {
  if (!iso) return "";
  const then = new Date(iso.length <= 10 ? `${iso}T00:00:00Z` : iso).getTime();
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (Number.isNaN(days)) return "";
  if (days <= 0) return "today";
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}

/** Pay as the reader should see it, and whether it is stated, estimated or bad. */
export function payOf(job: Job): { text: string; tone: "good" | "bad" | "plain" | "none" } {
  const bad = job.pay_verdict === "low";
  if (job.pay_verdict === "unpaid") return { text: "Unpaid", tone: "bad" };
  if (job.pay_verdict === "suspicious") return { text: "Looks fake", tone: "bad" };
  if (/month/i.test(job.salary_text) && job.salary_min_lpa != null && job.salary_max_lpa != null) {
    // Stipends are stored annualised; show them per month, the way they are quoted.
    const k = (lpa: number) => Math.round((lpa * 100) / 12);
    const lo = k(job.salary_min_lpa), hi = k(job.salary_max_lpa);
    return { text: `₹${lo === hi ? lo : `${lo}–${hi}`}k/mo`, tone: bad ? "bad" : "good" };
  }
  if (job.salary_min_lpa != null && job.salary_max_lpa != null) {
    const range = job.salary_min_lpa === job.salary_max_lpa
      ? `${job.salary_min_lpa}` : `${job.salary_min_lpa}–${job.salary_max_lpa}`;
    return { text: `₹${range} LPA`, tone: bad ? "bad" : "good" };
  }
  if (job.est_max_lpa != null) {
    return { text: `~₹${job.est_min_lpa}–${job.est_max_lpa} LPA`, tone: bad ? "bad" : "plain" };
  }
  if (job.salary_text) return { text: job.salary_text, tone: "plain" };
  return { text: "—", tone: "none" };
}

export function expOf(job: Job): string {
  if (job.exp_min == null) return "—";
  if (job.exp_max != null && job.exp_max !== job.exp_min) return `${job.exp_min}–${job.exp_max} yr`;
  return job.exp_min === 0 ? "Fresher" : `${job.exp_min}+ yr`;
}

export function placeOf(job: Job): string {
  const where = job.cities.length ? job.cities.join(", ") : job.location;
  return job.is_remote && !/remote/i.test(where) ? `${where}, Remote` : where;
}

export const TONE = { good: "text-good", bad: "text-bad", plain: "text-ink", none: "text-faint" };

export const STATUS: Record<string, { label: string; dot: string }> = {
  saved: { label: "Shortlisted", dot: "bg-mark" },
  applied: { label: "Applied", dot: "bg-ink" },
  interview: { label: "Interview", dot: "bg-warn" },
  offer: { label: "Offer", dot: "bg-good" },
  rejected: { label: "Rejected", dot: "bg-bad" },
};
