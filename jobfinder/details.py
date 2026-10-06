"""Second pass: fetch the full posting for jobs whose listing had no description.

Workday and SmartRecruiters list titles only, so the description, real
location list and employment type come from one extra request per job. Each
job is fetched once; `detail_done` marks it so later runs skip it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlparse

import httpx

from . import db, enrich, pay, score
from .sources import UA

logger = logging.getLogger("jobfinder.details")

PER_HOST = 3          # concurrent detail requests against one host
MAX_PER_RUN = 12000   # backstop so a first run cannot go on forever

_LD_JSON = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)


async def _workday(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url, headers={"Accept": "application/json", "User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    info = resp.json().get("jobPostingInfo") or {}
    locations = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
    country = (info.get("country") or {}).get("descriptor")
    if country:
        locations.append(country)
    return {
        "description_html": info.get("jobDescription") or "",
        "location": "; ".join(dict.fromkeys(x for x in locations if x)),
        "employment_type": info.get("timeType") or "",
        "posted_at": (info.get("startDate") or "")[:10],
    }


async def _smartrecruiters(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url, timeout=30)
    resp.raise_for_status()
    sections = ((resp.json().get("jobAd") or {}).get("sections") or {})
    html = "\n".join(
        f"<h3>{s.get('title', '')}</h3>{s.get('text', '')}"
        for key in ("jobDescription", "qualifications", "additionalInformation")
        if (s := sections.get(key))
    )
    return {"description_html": html}


def _find_posting(node) -> dict | None:
    if isinstance(node, dict):
        if node.get("@type") == "JobPosting" or "JobPosting" in (node.get("@type") or []):
            return node
        for value in node.values():
            if (hit := _find_posting(value)):
                return hit
    elif isinstance(node, list):
        for item in node:
            if (hit := _find_posting(item)):
                return hit
    return None


async def _jsonld(client: httpx.AsyncClient, url: str) -> dict:
    """Generic fallback: schema.org JobPosting markup on the public job page."""
    resp = await client.get(
        url, headers={"Accept": "text/html", "User-Agent": UA}, timeout=30
    )
    resp.raise_for_status()
    for block in _LD_JSON.findall(resp.text):
        try:
            posting = _find_posting(json.loads(block.strip()))
        except json.JSONDecodeError:
            continue
        if not posting:
            continue
        out = {
            "description_html": posting.get("description") or "",
            "employment_type": posting.get("employmentType") or "",
            "posted_at": str(posting.get("datePosted") or "")[:10],
        }
        if isinstance(out["employment_type"], list):
            out["employment_type"] = ", ".join(out["employment_type"])
        value = (posting.get("baseSalary") or {}).get("value") if isinstance(
            posting.get("baseSalary"), dict) else None
        if isinstance(value, dict):
            out["salary_struct"] = {
                "min": value.get("minValue") or value.get("value"),
                "max": value.get("maxValue") or value.get("value"),
                "currency": (posting.get("baseSalary") or {}).get("currency"),
                "interval": str(value.get("unitText") or "year").lower(),
            }
        return out
    return {}


async def _html(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(
        url, headers={"Accept": "text/html", "User-Agent": UA}, timeout=30
    )
    resp.raise_for_status()
    return resp.text


async def _linkedin(client: httpx.AsyncClient, url: str) -> dict:
    from .feeds import parse_linkedin_detail
    return parse_linkedin_detail(await _html(client, url))


async def _internshala(client: httpx.AsyncClient, url: str) -> dict:
    from .feeds import parse_internshala_detail
    return parse_internshala_detail(await _html(client, url))


async def _pcsx(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    return {
        "description_html": data.get("jobDescription") or "",
        "location": "; ".join(data.get("locations") or []),
    }


_KINDS = {"workday": _workday, "smartrecruiters": _smartrecruiters, "jsonld": _jsonld,
          "linkedin": _linkedin, "internshala": _internshala, "pcsx": _pcsx}

# LinkedIn throttles hard, so its detail pages are fetched one at a time and
# only for the best-scoring jobs each run; the rest keep their listing data.
SLOW_KINDS = {"linkedin": (1, 1.5, 400)}   # kind -> (concurrency, pause seconds, per-run cap)


def _apply(job: dict, detail: dict, profile: dict) -> dict | None:
    """Merge a detail response into a job row. None means 'not an India job'."""
    description = enrich.html_to_text(detail.get("description_html")) or job.get("description") or ""
    location = detail.get("location") or job.get("location") or ""
    place = enrich.locate(location)
    if job.get("scope") == "unknown" and place["scope"] in ("abroad", "unknown"):
        return None
    if place["scope"] in ("abroad", "unknown"):
        # The listing already established India; keep that and its location text.
        place = enrich.locate(job.get("location"))
        place = {**place, "in_india": True, "scope": "india"}
        location = job.get("location") or location

    exp_min, exp_max = enrich.parse_experience(description)
    raw_type = detail.get("employment_type") or job.get("employment_type")
    employment = enrich.classify_employment(raw_type, job["title"])
    salary = enrich.parse_salary(description, detail.get("salary_struct"))
    if salary["max_lpa"] is None and job.get("salary_max_lpa") is not None:
        # The listing stated pay (e.g. an Internshala stipend) that the detail page
        # does not repeat; keep it rather than blanking it.
        salary = {"min_lpa": job["salary_min_lpa"], "max_lpa": job["salary_max_lpa"],
                  "text": job.get("salary_text") or ""}
    job.update(
        description=description, location=location, cities=place["cities"],
        is_remote=int(place["remote"]), scope=place["scope"],
        exp_min=exp_min, exp_max=exp_max, employment_type=employment,
        level=enrich.classify_level(job["title"], exp_min, employment),
        salary_min_lpa=salary["min_lpa"], salary_max_lpa=salary["max_lpa"],
        salary_text=salary["text"] or job.get("salary_text") or "",
        posted_at=enrich.iso_date(detail.get("posted_at")) or job.get("posted_at") or "",
        detail_done=1,
    )
    pay.apply_band(job)
    job["pay_verdict"] = pay.judge(job, profile)
    job["score"], job["score_reasons"] = score.score_job(job, profile)
    return job


async def fetch_pending_details(client: httpx.AsyncClient, conn, profile: dict) -> int:
    marks = ",".join("?" * len(SLOW_KINDS))
    rows = conn.execute(
        "SELECT * FROM jobs WHERE is_active=1 AND detail_done=0 "
        f"AND COALESCE(detail_kind, '') NOT IN ({marks}) "
        "ORDER BY is_tech DESC, score DESC LIMIT ?", (*SLOW_KINDS, MAX_PER_RUN),
    ).fetchall()
    for kind, (_, _, cap) in SLOW_KINDS.items():
        rows += conn.execute(
            "SELECT * FROM jobs WHERE is_active=1 AND detail_done=0 AND detail_kind=? "
            "ORDER BY is_tech DESC, score DESC LIMIT ?", (kind, cap),
        ).fetchall()
    if not rows:
        return 0
    logger.info("Fetching details for %d jobs", len(rows))
    host_sems: dict[str, asyncio.Semaphore] = {}
    done = 0

    async def one(row) -> None:
        nonlocal done
        job = db.job_to_dict(row)
        kind = job.get("detail_kind") or "jsonld"
        url = job.get("detail_url") or job["apply_url"]
        limit, pause, _ = SLOW_KINDS.get(kind, (PER_HOST, 0.25, 0))
        sem = host_sems.setdefault(urlparse(url).netloc, asyncio.Semaphore(limit))
        async with sem:
            try:
                detail = await _KINDS.get(kind, _jsonld)(client, url)
            except (httpx.HTTPError, ValueError) as exc:
                logger.debug("detail failed %s: %s", url, exc)
                status = getattr(getattr(exc, "response", None), "status_code", 0)
                if 400 <= status < 500 and status != 429:
                    # Permanent refusal: stop retrying this job on every run.
                    conn.execute("UPDATE jobs SET detail_done=1 WHERE id=?", (job["id"],))
                    conn.commit()
                return
            await asyncio.sleep(pause)
        merged = _apply(job, detail, profile)
        if merged is None:
            conn.execute("DELETE FROM jobs WHERE id=?", (job["id"],))
            conn.commit()
            return
        conn.execute(
            "UPDATE jobs SET description=?, location=?, cities=?, is_remote=?, scope=?, "
            "exp_min=?, exp_max=?, employment_type=?, level=?, salary_min_lpa=?, "
            "salary_max_lpa=?, salary_text=?, posted_at=?, detail_done=1, score=?, "
            "score_reasons=?, pay_verdict=?, est_min_lpa=?, est_max_lpa=?, est_source=? "
            "WHERE id=?",
            (merged["description"], merged["location"], json.dumps(merged["cities"]),
             merged["is_remote"], merged["scope"], merged["exp_min"], merged["exp_max"],
             merged["employment_type"], merged["level"], merged["salary_min_lpa"],
             merged["salary_max_lpa"], merged["salary_text"], merged["posted_at"],
             merged["score"], json.dumps(merged["score_reasons"]), merged["pay_verdict"],
             merged.get("est_min_lpa"), merged.get("est_max_lpa"), merged.get("est_source"),
             job["id"]),
        )
        done += 1
        # Commit per job: a long-open write transaction would block the web
        # app from saving application status while a refresh is running.
        conn.commit()

    await asyncio.gather(*(one(r) for r in rows))
    conn.commit()
    return done
