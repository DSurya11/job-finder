"""Workday ATS fetcher (undocumented CXS API).

Endpoint:
  POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

Response shape:
  { "jobPostings": [ { "title", "externalPath", "locationsText",
                        "postedOn", "bulletFields": [...] } ],
    "total": 500 }

Detail endpoint (optional, for timeType):
  GET https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}

IMPORTANT: Protected by Akamai bot detection.
  - Realistic User-Agent + Origin/Referer headers required
  - Rate-limited: configurable delay between requests (default 3s)
  - Retries with exponential backoff on 403/429
  - If blocked, logs warning and returns partial results
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Rotate through realistic browser User-Agents
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 "
    "Firefox/128.0",
]

PAGE_SIZE = 20
MAX_RETRIES = 3
MAX_PAGES = 250  # safety cap: 250 pages × 20 = 5000 jobs max per company


def _build_base_url(tenant: str, wd_instance: str, site: str) -> str:
    return f"https://{tenant}.{wd_instance}.myworkdayjobs.com"


def _build_headers(base_url: str, site: str) -> dict[str, str]:
    ua = random.choice(_USER_AGENTS)
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": ua,
        "Origin": base_url,
        "Referer": f"{base_url}/{site}",
    }


def _extract_employment_type(posting: dict) -> str:
    """Extract employment type from a Workday job posting.

    The actual Workday response has `timeType` as a top-level string field
    (e.g. "Full time") on some tenants.  `bulletFields` is a list of plain
    strings (usually just the requisition ID) — NOT a list of dicts.
    """
    # Primary: top-level timeType field (present on Palo Alto, some others)
    time_type = posting.get("timeType", "")
    if time_type:
        return time_type

    # Fallback: check if any bulletField string looks like a time type
    for field in posting.get("bulletFields", []):
        if isinstance(field, str):
            fl = field.lower()
            if "full time" in fl or "full-time" in fl:
                return "Full time"
            if "part time" in fl or "part-time" in fl:
                return "Part time"
            if "intern" in fl:
                return "Internship"
        elif isinstance(field, dict):
            # Some tenants *may* use dict format — handle defensively
            label = (field.get("label") or field.get("type") or "").lower()
            value = field.get("value") or field.get("display") or ""
            if any(kw in label for kw in ("time type", "employment", "job type")):
                return value

    return "Unknown"


def _normalise(posting: dict, company_name: str, base_url: str, site: str) -> dict:
    """Map Workday job posting -> common schema."""
    ext_path = posting.get("externalPath", "")

    # Build apply URL from external path
    apply_url = f"{base_url}/{site}{ext_path}" if ext_path else ""

    # Extract remote type if available (top-level field on some tenants)
    location = posting.get("locationsText", "")
    remote_type = posting.get("remoteType", "")
    if remote_type and remote_type.lower() != "on-site":
        location = f"{location} ({remote_type})" if location else remote_type

    return {
        "company": company_name,
        "title": posting.get("title", ""),
        "location": location,
        "employment_type": _extract_employment_type(posting),
        "description": "",  # list endpoint has no description; detail fetch is optional
        "apply_url": apply_url,
        "ats_source": "Workday",
        "departments": "",
        "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


async def _fetch_page(
    client: httpx.AsyncClient,
    jobs_url: str,
    headers: dict,
    offset: int,
    search_text: str = "",
) -> tuple[list[dict], int]:
    """Fetch one page of Workday job listings.

    Returns:
        (job_postings list, total count)
    """
    body = {
        "appliedFacets": {},
        "limit": PAGE_SIZE,
        "offset": offset,
        "searchText": search_text,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.post(
                jobs_url, json=body, headers=headers, timeout=30
            )
            if resp.status_code in (403, 429):
                wait = (2 ** attempt) + random.uniform(0.5, 2.0)
                logger.warning(
                    "[Workday] %d at offset %d — retry %d/%d in %.1fs",
                    resp.status_code, offset, attempt, MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("jobPostings", []), data.get("total", 0)
        except httpx.HTTPStatusError as exc:
            logger.warning("[Workday] HTTP %s at offset %d", exc.response.status_code, offset)
            return [], 0
        except httpx.RequestError as exc:
            logger.warning("[Workday] request error at offset %d: %s", offset, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                continue
            return [], 0

    # All retries exhausted
    logger.error("[Workday] all %d retries exhausted at offset %d", MAX_RETRIES, offset)
    return [], 0


async def fetch_workday(
    client: httpx.AsyncClient,
    tenant: str,
    wd_instance: str,
    site: str,
    company_name: str,
    search_text: str = "",
    delay: float = 3.0,
) -> list[dict]:
    """Fetch all jobs from a Workday career site.

    Args:
        client: Shared httpx async client.
        tenant: Workday tenant (e.g. "nvidia").
        wd_instance: Workday datacenter (e.g. "wd5").
        site: Career site identifier (e.g. "NVIDIAExternalCareerSite").
        company_name: Human-readable name for logging.
        delay: Seconds to wait between paginated requests (default 3.0).

    Returns:
        List of normalised job dicts.
    """
    base_url = _build_base_url(tenant, wd_instance, site)
    jobs_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"
    headers = _build_headers(base_url, site)

    all_jobs: list[dict] = []
    offset = 0
    total = None

    for page in range(MAX_PAGES):
        postings, total_count = await _fetch_page(client, jobs_url, headers, offset, search_text)

        if total is None:
            total = total_count
            logger.info("[Workday/%s] total jobs reported: %d", company_name, total)

        if not postings:
            if page == 0:
                logger.warning(
                    "[Workday/%s] no results on first page — may be blocked "
                    "or wrong tenant/site config",
                    company_name,
                )
            break

        for p in postings:
            all_jobs.append(_normalise(p, company_name, base_url, site))

        offset += PAGE_SIZE

        # Use `total` (from page 0), since subsequent pages often return `total: 0`
        if total is not None and offset >= total:
            break

        # Rate-limit: wait between pages with some jitter
        jitter = random.uniform(0.5, 1.5)
        await asyncio.sleep(delay + jitter)

    logger.info("[Workday/%s] fetched %d jobs (of %s total)", company_name, len(all_jobs), total)
    return all_jobs
