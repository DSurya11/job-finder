"""Fetch every company, keep India-eligible jobs, enrich, store, and track health.

A company counts as healthy only if its fetch succeeded AND returned at least
as many raw postings as a sanity floor relative to its previous run. Anything
else is surfaced in the coverage report instead of being silently dropped.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path

import httpx
import yaml

from . import db, enrich, pay, score
from .feeds import FEEDS
from .sources import ADAPTERS as ATS_ADAPTERS, CONCURRENCY, UA

ADAPTERS = {**ATS_ADAPTERS, **FEEDS}
# Postings from these belong to many companies and are never the only copy we want.
AGGREGATORS = {"linkedin", "internshala"}
AGGREGATOR_TTL_DAYS = 14

logger = logging.getLogger("jobfinder")

COMPANIES_PATH = Path(__file__).resolve().parent.parent / "companies.yaml"

# Live progress for the UI; a run happens in one process so a dict is enough.
PROGRESS: dict = {"running": False, "done": 0, "total": 0, "current": "", "last": None}


def load_companies(path: Path | str | None = None) -> list[dict]:
    data = yaml.safe_load(Path(path or COMPANIES_PATH).read_text(encoding="utf-8")) or {}
    return [c for c in data.get("companies", []) if c.get("enabled", True)]


def match_key(company: str, title: str) -> str:
    """Loose identity used to drop an aggregator copy of a job we already have."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", "", t.lower())
    company = re.sub(r"\b(india|pvt|private|ltd|limited|inc|llc|technologies|technology|"
                     r"labs|software|corporation|corp|group)\b\.?", "", company.lower())
    return f"{norm(company)}|{norm(title)}"


def job_id(company: str, raw: dict) -> str:
    key = raw.get("apply_url") or f"{raw.get('title')}|{raw.get('location')}"
    return hashlib.sha1(f"{company.lower()}|{key}".encode()).hexdigest()[:16]


_NAV_TITLE = re.compile(
    r"^(skip to|home|careers?|jobs?|apply now|back to|why work here|main content|"
    r"view all|learn more|search)\b", re.I,
)


def build_job(company: dict, raw: dict, profile: dict) -> dict | None:
    """Raw posting -> stored row, or None if it is not an India-eligible job."""
    title = re.sub(r"\s+", " ", raw.get("title") or "").strip()
    if len(title) < 4 or _NAV_TITLE.match(title) or not raw.get("apply_url"):
        return None

    location = (raw.get("location") or "").strip()
    place = enrich.locate(location)
    if raw.get("india_confirmed") and not place["in_india"]:
        place = {**place, "in_india": True, "scope": "india"}
    if place["scope"] == "abroad":
        return None
    if place["scope"] == "unknown" and not (raw.get("detail_url") or company.get("india_only")):
        return None
    if company.get("india_only") and place["scope"] != "india":
        place = {**place, "in_india": True, "scope": "india"}

    description = enrich.html_to_text(raw.get("description_html")) or (raw.get("description") or "")
    if re.search(r"<(br|p|li|ul|div|h\d|strong)\b", description):
        description = enrich.html_to_text(description)        # a source that sent markup as text
    departments = raw.get("departments") or ""
    exp_min, exp_max = enrich.parse_experience(description)
    employment = enrich.classify_employment(raw.get("employment_type"), title)
    role, is_tech = enrich.classify_role(title, departments)
    salary = enrich.parse_salary(description, raw.get("salary_struct"))

    name = re.sub(r"\s+", " ", raw.get("company") or company["name"]).strip()
    job = {
        "id": job_id(name, raw),
        "company": name,
        "title": title,
        "location": location or ("India" if place["in_india"] else ""),
        "cities": place["cities"],
        "is_remote": int(place["remote"]),
        "scope": place["scope"],
        "employment_type": employment,
        "level": enrich.classify_level(title, exp_min, employment),
        "role": role,
        "is_tech": int(is_tech),
        "exp_min": exp_min,
        "exp_max": exp_max,
        "salary_min_lpa": salary["min_lpa"],
        "salary_max_lpa": salary["max_lpa"],
        "salary_text": salary["text"],
        "description": description,
        "departments": departments,
        "apply_url": raw["apply_url"],
        "source": company["ats"],
        "posted_at": enrich.iso_date(raw.get("posted_at")),
        "detail_kind": raw.get("detail_kind"),
        "detail_url": raw.get("detail_url"),
        "detail_done": int(bool(description) and not raw.get("detail_url")),
    }
    pay.apply_band(job)
    job["pay_verdict"] = pay.judge(job, profile)
    job["score"], job["score_reasons"] = score.score_job(job, profile)
    return job


async def _fetch_company(client, company: dict, sems: dict) -> dict:
    ats = company.get("ats", "")
    adapter = ADAPTERS.get(ats)
    result = {"company": company, "raw": [], "error": "", "seconds": 0.0}
    if not adapter:
        result["error"] = f"no adapter for ats '{ats}'"
        return result
    started = time.monotonic()
    async with sems.setdefault(ats, asyncio.Semaphore(CONCURRENCY.get(ats, 4))):
        try:
            result["raw"] = await asyncio.wait_for(
                adapter(client, company), timeout=company.get("timeout", 600)
            )
        except httpx.HTTPStatusError as exc:
            result["error"] = f"HTTP {exc.response.status_code}"
        except asyncio.TimeoutError:
            result["error"] = "timed out"
        except Exception as exc:  # one broken board must not sink the run
            result["error"] = f"{type(exc).__name__}: {exc}"[:200]
    result["seconds"] = round(time.monotonic() - started, 1)
    PROGRESS["done"] += 1
    PROGRESS["current"] = company["name"]
    return result


def health_status(ok: bool, raw: int, india: int, previous: int | None) -> str:
    if not ok:
        return "failed"
    if raw == 0:
        return "empty"
    if previous and india < previous * 0.4 and previous - india >= 5:
        return "dropped"
    return "ok"


async def run(companies: list[dict] | None = None, with_details: bool = True) -> dict:
    """One full refresh. Returns a summary dict."""
    companies = companies or load_companies()
    profile = score.load_profile()
    conn = db.connect()
    started = db.now()
    run_id = conn.execute("INSERT INTO runs (started) VALUES (?)", (started,)).lastrowid
    conn.commit()
    previous = db.previous_counts(conn)
    PROGRESS.update(running=True, done=0, total=len(companies), current="")

    sems: dict = {}
    limits = httpx.Limits(max_connections=40, max_keepalive_connections=20)
    async with httpx.AsyncClient(
        follow_redirects=True, limits=limits,
        headers={"Accept": "application/json", "User-Agent": UA},
    ) as client:
        results = await asyncio.gather(*(_fetch_company(client, c, sems) for c in companies))

        raw_total = india_total = new_total = closed_total = 0
        report = []
        # Company boards first, so aggregator copies of the same job can be dropped.
        results.sort(key=lambda r: r["company"].get("ats") in AGGREGATORS)
        direct_keys: set[str] | None = None
        for res in results:
            company = res["company"]
            is_aggregator = company.get("ats") in AGGREGATORS
            jobs = [j for j in (build_job(company, r, profile) for r in res["raw"]) if j]
            # The same posting can be listed once per location with one URL.
            jobs = list({j["id"]: j for j in jobs}.values())
            if is_aggregator:
                if direct_keys is None:
                    marks = ",".join("?" * len(AGGREGATORS))
                    direct_keys = {
                        match_key(r["company"], r["title"]) for r in conn.execute(
                            f"SELECT company, title FROM jobs WHERE is_active=1 "
                            f"AND source NOT IN ({marks})", tuple(AGGREGATORS))
                    }
                jobs = [j for j in jobs if match_key(j["company"], j["title"]) not in direct_keys]
            ok = not res["error"]
            status = health_status(ok, len(res["raw"]), len(jobs), previous.get(company["name"]))
            new_total += db.upsert_jobs(conn, jobs, started)
            # Only retire old postings when we trust this fetch.
            if status == "ok" and is_aggregator:
                # A search feed never returns everything, so absence from one run
                # proves nothing; retire by age instead.
                closed_total += conn.execute(
                    "UPDATE jobs SET is_active=0 WHERE source=? AND is_active=1 "
                    "AND last_seen < datetime('now', ?)",
                    (company["ats"], f"-{AGGREGATOR_TTL_DAYS} days"),
                ).rowcount
            elif status == "ok":
                closed_total += db.close_missing(conn, company["name"], started)
            conn.execute(
                "INSERT INTO company_runs VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, company["name"], company.get("ats"), int(ok), len(res["raw"]),
                 len(jobs), res["error"], res["seconds"], started),
            )
            conn.commit()
            raw_total += len(res["raw"])
            india_total += len(jobs)
            report.append({
                "company": company["name"], "ats": company.get("ats"), "status": status,
                "raw": len(res["raw"]), "india": len(jobs), "error": res["error"],
                "previous": previous.get(company["name"]), "seconds": res["seconds"],
            })
        conn.commit()

        details = 0
        if with_details:
            from .details import fetch_pending_details
            PROGRESS["current"] = "job descriptions"
            details = await fetch_pending_details(client, conn, profile)

    # Re-apply salary-site pay already looked up; new jobs at known companies get it free.
    from .portal import apply_cached
    apply_cached(conn, profile)

    conn.execute(
        "UPDATE runs SET finished=?, raw_total=?, india_total=?, new_jobs=?, closed_jobs=? WHERE id=?",
        (db.now(), raw_total, india_total, new_total, closed_total, run_id),
    )
    conn.commit()
    conn.close()
    summary = {
        "run_id": run_id, "companies": len(companies), "raw_total": raw_total,
        "india_total": india_total, "new_jobs": new_total, "closed_jobs": closed_total,
        "details_fetched": details,
        "problems": [r for r in report if r["status"] != "ok"], "report": report,
    }
    PROGRESS.update(running=False, current="", last={k: v for k, v in summary.items() if k != "report"})
    return summary


def print_summary(summary: dict) -> None:
    print(f"\nCompanies fetched : {summary['companies']}")
    print(f"Raw postings      : {summary['raw_total']}")
    print(f"India-eligible    : {summary['india_total']}")
    print(f"New / closed      : {summary['new_jobs']} / {summary['closed_jobs']}")
    print(f"Details fetched   : {summary['details_fetched']}")
    problems = summary["problems"]
    print(f"Companies needing attention: {len(problems)}")
    for p in sorted(problems, key=lambda r: r["status"]):
        note = p["error"] or (f"was {p['previous']}, now {p['india']}" if p["status"] == "dropped" else "0 postings")
        print(f"  [{p['status']:7}] {p['company']:28} {p['ats']:16} {note}")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("report", "problems")}))
