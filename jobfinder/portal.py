"""Pay from AmbitionBox: reported salaries per company, designation and experience.

For a job with no stated pay we look up the company's salary page for the
closest designation and take the bucket for the experience the job asks for.
Every lookup (hit or miss) is cached in the database, so a company and
designation pair is requested once.

  python -m jobfinder pay --limit 300
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from . import db, pay, score
from .sources import UA

logger = logging.getLogger("jobfinder.portal")

BASE = "https://www.ambitionbox.com/salaries"
_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

# AmbitionBox's page name where it differs from a plain slug of our company name.
COMPANY_SLUGS = {
    "tower research": "tower-research-capital", "de shaw": "d-e-shaw", "jpmorgan chase": "jpmorgan-chase-co",
    "walmart global tech": "walmart-global-tech-india", "sap labs india": "sap", "lowe's india": "lowes",
    "samsung r&d": "samsung-research", "hpe": "hewlett-packard-enterprise", "ge healthcare": "ge-healthcare",
    "imc trading": "imc-trading", "graviton research": "graviton-research-capital", "fi money": "epifi",
    "s&p global": "s-and-p-global", "at&t": "at-and-t", "nvidia": "nvidia", "bp": "bp",
}
# Fallback designations by role family, used when the job's own title has no page.
ROLE_DESIGNATION = {
    "Software Engineering": "software-engineer", "Backend": "software-engineer",
    "Full Stack": "full-stack-developer", "Frontend": "frontend-developer", "Mobile": "android-developer",
    "ML / AI": "machine-learning-engineer", "Data Science": "data-scientist",
    "Data Engineering": "data-engineer", "Data Analyst": "data-analyst", "DevOps / SRE": "devops-engineer",
    "QA / SDET": "qa-engineer", "Security": "security-engineer", "Embedded / Hardware": "design-engineer",
}
SPELLINGS = {
    "frontend-developer": "front-end-developer", "frontend-engineer": "front-end-developer",
    "backend-developer": "back-end-developer", "backend-engineer": "back-end-developer",
    "fullstack-developer": "full-stack-developer", "fullstack-engineer": "full-stack-developer",
    "full-stack-engineer": "full-stack-developer", "sde": "software-development-engineer",
    "sde-intern": "software-engineer-intern", "sdet": "software-development-engineer-in-test",
    "ml-engineer": "machine-learning-engineer", "ai-engineer": "artificial-intelligence-engineer",
    "devops": "devops-engineer", "qa": "qa-engineer",
}
LEVEL_PREFIX = {"Senior": "senior-", "Staff+": "principal-", "Manager": ""}
LEVEL_YEARS = {"Intern": 0, "Entry": 0, "Mid": 3, "Senior": 6, "Staff+": 10, "Manager": 10}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def company_slug(company: str) -> str:
    return COMPANY_SLUGS.get(company.lower().strip(), slug(company))


def designations(job: dict) -> list[str]:
    """Designation pages to try for a job, most specific first."""
    title = re.sub(r"\(.*?\)|\[.*?\]", " ", job.get("title") or "")
    title = re.split(r"\s[-–—|:]\s|,|/", title)[0]
    title = re.sub(r"\b(i{1,3}|iv|v|[1-5])\b\s*$", "", title.strip(), flags=re.I)
    out = [slug(title)] if 3 <= len(slug(title)) <= 40 else []
    base = ROLE_DESIGNATION.get(job.get("role") or "")
    level = job.get("level") or "Unspecified"
    if base:
        if level == "Intern":
            out += [f"{base}-intern", "intern"]
        elif level in LEVEL_PREFIX and LEVEL_PREFIX[level]:
            out += [LEVEL_PREFIX[level] + base, base]
        elif level == "Manager":
            out += ["engineering-manager"]
        else:
            out += [base]
    elif level == "Intern":
        out += ["intern"]
    # AmbitionBox spells a few designations differently from how postings do.
    out = [alias for d in out for alias in (d, SPELLINGS.get(d)) if alias]
    return list(dict.fromkeys(out))[:4]


def _same_company(wanted: str, found: str) -> bool:
    """A missing page redirects to an unrelated company; accept only a real match."""
    norm = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(
        r"\b(india|pvt|private|ltd|limited|inc|technologies|technology|labs|group|corporation|"
        r"capital|research|global|tech|systems|software|company|co)\b", "", s.lower()))
    a, b = norm(wanted), norm(found)
    return bool(a and b) and (a in b or b in a)


async def lookup(client: httpx.AsyncClient, company: str, designation: str) -> dict:
    """Fetch one company/designation page. Returns {"found": bool, ...}."""
    url = f"{BASE}/{company_slug(company)}-salaries/{designation}"
    miss = {"found": 0, "url": url}
    resp = await client.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=30)
    if resp.status_code == 404:
        return miss
    resp.raise_for_status()
    match = _NEXT.search(resp.text)
    if not match:
        return miss
    props = json.loads(match.group(1)).get("props", {}).get("pageProps", {})
    ld = props.get("occupationalJSONLD") or {}
    data = ((props.get("salaryData") or {}).get("data")) or {}
    summary = data.get("summaryData") or {}
    org = (ld.get("hiringOrganization") or {}).get("name") or ""
    if not summary.get("totalSalaryDataPoints") or not _same_company(company, org):
        return miss
    return {
        "found": 1, "url": url, "org": org, "title": ld.get("name") or designation,
        "samples": int(summary["totalSalaryDataPoints"]),
        "avg": summary.get("totalSalaryAverage"),
        "min": summary.get("minCtc"), "max": summary.get("maxCtc"),
        "levels": [
            {k: lv.get(k) for k in ("minExp", "maxExp", "minCtc", "maxCtc", "avgCtc", "count")}
            for lv in data.get("experienceLevels") or []
        ],
    }


def estimate(job: dict, record: dict) -> dict | None:
    """Pick the pay range in `record` for the experience this job asks for."""
    lpa = lambda rupees: round(float(rupees) / 1e5, 1)
    years = job.get("exp_min")
    if years is None:
        years = LEVEL_YEARS.get(job.get("level") or "")
    levels = [lv for lv in record.get("levels") or [] if lv.get("minCtc") and lv.get("maxCtc")
              and lv.get("avgCtc") and lv.get("minExp") is not None and lv.get("maxExp") is not None]
    if years is not None and levels:
        # The bucket containing that many years, or the nearest one below/above.
        bucket = min(levels, key=lambda lv: 0 if lv["minExp"] <= years < lv["maxExp"]
                     else min(abs(lv["minExp"] - years), abs(lv["maxExp"] - years)) + 0.5)
        span = (f"{bucket['minExp']:g}–{bucket['maxExp']:g} yr experience"
                if bucket["minExp"] else "freshers")
        return {
            "min": lpa(bucket["minCtc"]), "max": lpa(bucket["maxCtc"]),
            "note": f"AmbitionBox: {record['title']} at {record['org']}, {span} — average "
                    f"₹{lpa(bucket['avgCtc'])} L from {bucket['count']} reported salaries.",
        }
    if record.get("min") and record.get("max"):
        return {
            "min": lpa(record["min"]), "max": lpa(record["max"]),
            "note": f"AmbitionBox: {record['title']} at {record['org']}, all experience levels — "
                    f"average ₹{lpa(record['avg'])} L from {record['samples']} reported salaries.",
        }
    return None


MARKET = "*"      # cache key for role-wide (not company-specific) pages


async def lookup_market(client: httpx.AsyncClient, designation: str) -> dict:
    """India-wide pay for a designation across all companies, by experience."""
    url = f"https://www.ambitionbox.com/profile/{designation}-salary"
    miss = {"found": 0, "url": url}
    resp = await client.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=30)
    if resp.status_code == 404:
        return miss
    resp.raise_for_status()
    match = _NEXT.search(resp.text)
    if not match:
        return miss
    props = json.loads(match.group(1)).get("props", {}).get("pageProps", {})
    data = (props.get("salaryData") or {}).get("profileSalaryData") or {}
    if not data.get("totalDatapoints") or not data.get("medianCtc"):
        return miss
    buckets = []
    for b in data.get("experienceDistribution") or []:
        years = re.findall(r"\d+", str(b.get("years") or ""))
        if years and b.get("averageCtc"):
            buckets.append({"lo": int(years[0]), "hi": int(years[-1]), "avg": b["averageCtc"],
                            "sd": b.get("stdDevCtc") or 0, "count": b.get("datapoints") or 0})
    return {"found": 1, "url": url, "title": props.get("designation") or designation,
            "samples": int(data["totalDatapoints"]), "median": data["medianCtc"],
            "sd": data.get("stdDevCtc") or 0, "buckets": buckets}


def estimate_market(job: dict, record: dict) -> dict:
    """A one-standard-deviation band around the market average for the job's experience."""
    lpa = lambda rupees: round(float(rupees) / 1e5, 1)
    years = job.get("exp_min")
    if years is None:
        years = LEVEL_YEARS.get(job.get("level") or "")
    centre, spread, span, count = record["median"], record["sd"], "all experience levels", record["samples"]
    if years is not None and record.get("buckets"):
        b = min(record["buckets"], key=lambda b: 0 if b["lo"] <= years <= b["hi"]
                else min(abs(b["lo"] - years), abs(b["hi"] - years)) + 0.5)
        centre, spread, count = b["avg"], b["sd"], b["count"]
        span = f"{b['lo']}–{b['hi']} yr experience"
    low = max(float(centre) - float(spread) / 2, float(centre) * 0.6)
    return {
        "min": lpa(low), "max": lpa(float(centre) + float(spread) / 2),
        "note": f"AmbitionBox, all companies in India: {record['title']}, {span} — average "
                f"₹{lpa(centre)} L from {int(count):,} reported salaries. This company has no "
                "salary page, so the figure says nothing about what it pays in particular.",
    }


def _cache(conn) -> dict[tuple[str, str], dict]:
    return {(r["company"], r["designation"]): json.loads(r["data"])
            for r in conn.execute("SELECT company, designation, data FROM portal_pay")}


def apply_cached(conn, profile: dict | None = None) -> int:
    """Use cached lookups to set estimates on every job they cover. No network."""
    profile = profile or score.load_profile()
    cache = _cache(conn)
    if not cache:
        return 0
    updated = 0
    rows = conn.execute(
        "SELECT * FROM jobs WHERE is_active=1 AND salary_max_lpa IS NULL "
        "AND COALESCE(est_source, 'band') != 'claude'"
    ).fetchall()
    for row in rows:
        job = db.job_to_dict(row)
        for designation in designations(job):
            record = cache.get((job["company"], designation))
            est = estimate(job, record) if record and record.get("found") else None
            if not est:
                continue
            job.update(est_min_lpa=est["min"], est_max_lpa=est["max"], est_source="ambitionbox",
                       est_note=est["note"], est_url=record["url"])
            job["pay_verdict"] = pay.judge(job, profile)
            value, reasons = score.score_job(job, profile)
            conn.execute(
                "UPDATE jobs SET est_min_lpa=?, est_max_lpa=?, est_source='ambitionbox', est_note=?, "
                "est_url=?, pay_verdict=?, score=?, score_reasons=? WHERE id=?",
                (est["min"], est["max"], est["note"], record["url"], job["pay_verdict"], value,
                 json.dumps(reasons), job["id"]),
            )
            updated += 1
            break
        else:
            # No company page. If there is no pay-tier guess either, fall back to the
            # role's market-wide average so the row is not left blank.
            if job.get("est_source") not in (None, "market"):
                continue
            for designation in designations(job):
                record = cache.get((MARKET, designation))
                if not (record and record.get("found")):
                    continue
                est = estimate_market(job, record)
                job.update(est_min_lpa=est["min"], est_max_lpa=est["max"], est_source="market",
                           est_note=est["note"], est_url=record["url"])
                job["pay_verdict"] = pay.judge(job, profile)
                value, reasons = score.score_job(job, profile)
                conn.execute(
                    "UPDATE jobs SET est_min_lpa=?, est_max_lpa=?, est_source='market', est_note=?, "
                    "est_url=?, pay_verdict=?, score=?, score_reasons=? WHERE id=?",
                    (est["min"], est["max"], est["note"], record["url"], job["pay_verdict"], value,
                     json.dumps(reasons), job["id"]),
                )
                updated += 1
                break
    conn.commit()
    return updated


async def run(limit: int = 300, delay: float = 1.0, market_limit: int = 400) -> dict:
    """Look up pay for the best-matching jobs that still lack it."""
    profile = score.load_profile()
    conn = db.connect()
    cache = _cache(conn)
    # Best matches first, and only as many new company/designation pairs as `limit`.
    todo: list[tuple[str, str]] = []
    seen = set(cache)
    for row in conn.execute(
        "SELECT * FROM jobs WHERE is_active=1 AND salary_max_lpa IS NULL "
        "AND COALESCE(est_source, 'band') IN ('band', 'market') ORDER BY is_tech DESC, score DESC"
    ):
        job = db.job_to_dict(row)
        options = designations(job)
        if any(cache.get((job["company"], d), {}).get("found") for d in options):
            continue
        for d in options:
            if (job["company"], d) not in seen:
                seen.add((job["company"], d))
                todo.append((job["company"], d))
        if len(todo) >= limit:
            break
    todo = todo[:limit]

    hits = 0
    sem = asyncio.Semaphore(2)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(company: str, designation: str) -> None:
            nonlocal hits
            async with sem:
                try:
                    record = await lookup(client, company, designation)
                except httpx.HTTPError as exc:
                    logger.warning("AmbitionBox %s/%s: %s", company, designation, exc)
                    return                      # not cached, so it is retried next run
                await asyncio.sleep(delay)
            hits += record["found"]
            conn.execute("INSERT OR REPLACE INTO portal_pay VALUES (?,?,?,?)",
                         (company, designation, json.dumps(record), db.now()))
            conn.commit()

        await asyncio.gather(*(one(c, d) for c, d in todo))

        # Role-wide pages for whatever still has no figure at all. There are only a
        # few dozen distinct designations, so this is cheap.
        cache = _cache(conn)
        wanted: list[str] = []
        for row in conn.execute(
            "SELECT * FROM jobs WHERE is_active=1 AND salary_max_lpa IS NULL AND est_source IS NULL "
            "ORDER BY is_tech DESC, score DESC"
        ):
            job = db.job_to_dict(row)
            options = designations(job)
            if any(cache.get((job["company"], d), {}).get("found") for d in options):
                continue
            for d in options:
                if (MARKET, d) not in cache and d not in wanted:
                    wanted.append(d)
        market_hits = 0

        async def market(designation: str) -> None:
            nonlocal market_hits
            async with sem:
                try:
                    record = await lookup_market(client, designation)
                except httpx.HTTPError as exc:
                    logger.warning("AmbitionBox market %s: %s", designation, exc)
                    return
                await asyncio.sleep(delay)
            market_hits += record["found"]
            conn.execute("INSERT OR REPLACE INTO portal_pay VALUES (?,?,?,?)",
                         (MARKET, designation, json.dumps(record), db.now()))
            conn.commit()

        await asyncio.gather(*(market(d) for d in wanted[:market_limit]))
    updated = apply_cached(conn, profile)
    conn.close()
    return {"pages_requested": len(todo), "pages_with_data": hits,
            "market_pages_requested": len(wanted[:market_limit]), "market_pages_with_data": market_hits,
            "jobs_with_portal_pay": updated}
