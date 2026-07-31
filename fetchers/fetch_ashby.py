"""Ashby ATS fetcher.

Endpoint: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
No auth required. Returns all published postings for the job board.

Response shape:
  { "jobs": [ { "title", "location", "department", "team",
                "employmentType" ("FullTime", "PartTime", "Intern", …),
                "isRemote", "descriptionHtml", "descriptionPlain",
                "jobUrl", "applyUrl",
                "compensation": { ... } (optional) } ] }

The `employmentType` field is reliable for FTE vs intern filtering.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.ashbyhq.com/posting-api/job-board"


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:2000]


# Map Ashby's employmentType values to human-readable strings
_EMPLOYMENT_MAP = {
    "FullTime": "Full-time",
    "fullTime": "Full-time",
    "full_time": "Full-time",
    "PartTime": "Part-time",
    "partTime": "Part-time",
    "Intern": "Internship",
    "intern": "Internship",
    "Contract": "Contract",
    "contract": "Contract",
    "Contractor": "Contract",
}


def _normalise(job: dict, company_name: str) -> dict:
    """Map Ashby job → common schema."""
    emp_type_raw = job.get("employmentType", "")
    employment_type = _EMPLOYMENT_MAP.get(emp_type_raw, emp_type_raw or "Unknown")

    location = job.get("location", "")
    is_remote = job.get("isRemote", False)
    if is_remote and location:
        location = f"{location} (Remote)"
    elif is_remote:
        location = "Remote"

    desc_plain = job.get("descriptionPlain", "")
    desc_html = job.get("descriptionHtml", "")
    description = desc_plain[:2000] if desc_plain else _strip_html(desc_html)

    department = job.get("department", "")
    team = job.get("team", "")
    departments = ", ".join(filter(None, [department, team]))

    return {
        "company": company_name,
        "title": job.get("title", ""),
        "location": location,
        "employment_type": employment_type,
        "description": description,
        "apply_url": job.get("jobUrl", "") or job.get("applyUrl", ""),
        "ats_source": "Ashby",
        "departments": departments,
        "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


async def fetch_ashby(
    client: httpx.AsyncClient,
    slug: str,
    company_name: str,
) -> list[dict]:
    """Fetch all postings from an Ashby job board.

    Args:
        client: Shared httpx async client.
        slug: Ashby board slug (e.g. "cred").
        company_name: Human-readable company name for output.

    Returns:
        List of normalised job dicts.
    """
    url = f"{API_BASE}/{slug}"

    try:
        resp = await client.get(url, timeout=30)
        if resp.status_code == 404:
            logger.warning(
                "[Ashby/%s] 404 — slug '%s' not found", company_name, slug
            )
            return []
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "[Ashby/%s] HTTP %s — %s", company_name, exc.response.status_code, exc
        )
        return []
    except httpx.RequestError as exc:
        logger.warning("[Ashby/%s] request error: %s", company_name, exc)
        return []

    data = resp.json()
    raw_jobs = data.get("jobs", [])
    logger.info("[Ashby/%s] fetched %d raw jobs", company_name, len(raw_jobs))

    return [_normalise(j, company_name) for j in raw_jobs]
