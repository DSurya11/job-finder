"""Greenhouse ATS fetcher.

Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
No auth required. Returns ALL jobs at once (no pagination needed).

Response shape:
  { "jobs": [ { "title", "location": {"name"}, "absolute_url",
                "content" (HTML), "departments": [{"name"}],
                "offices": [{"name"}], "updated_at", "metadata" } ] }

Greenhouse has NO dedicated employment-type field — we rely on
title/content parsing in filter.py for intern vs FTE classification.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://boards-api.greenhouse.io/v1/boards"


def _strip_html(html: str) -> str:
    """Coarse HTML→plain-text for description storage."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:2000]


def _normalise(job: dict, company_name: str) -> dict:
    """Map Greenhouse job object → common schema."""
    departments = ", ".join(
        d.get("name", "") for d in (job.get("departments") or [])
    )
    offices = ", ".join(
        o.get("name", "") for o in (job.get("offices") or [])
    )
    location = (job.get("location") or {}).get("name", "") or offices

    raw_content = job.get("content", "")
    description = _strip_html(raw_content) if raw_content else ""

    return {
        "company": company_name,
        "title": job.get("title", ""),
        "location": location,
        "employment_type": "Unknown",  # Greenhouse has no field for this
        "description": description,
        "apply_url": job.get("absolute_url", ""),
        "ats_source": "Greenhouse",
        "departments": departments,
        "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "raw_content": raw_content,
    }


async def fetch_greenhouse(
    client: httpx.AsyncClient,
    slug: str,
    company_name: str,
) -> list[dict]:
    """Fetch all jobs from a Greenhouse job board.

    Args:
        client: Shared httpx async client.
        slug: Greenhouse board slug (e.g. "razorpaysoftwareprivatelimited").
        company_name: Human-readable company name for output.

    Returns:
        List of normalised job dicts.
    """
    url = f"{API_BASE}/{slug}/jobs"
    params = {"content": "true"}

    try:
        resp = await client.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "[Greenhouse/%s] HTTP %s — %s", company_name, exc.response.status_code, exc
        )
        return []
    except httpx.RequestError as exc:
        logger.warning("[Greenhouse/%s] request error: %s", company_name, exc)
        return []

    data = resp.json()
    raw_jobs = data.get("jobs", [])
    logger.info("[Greenhouse/%s] fetched %d raw jobs", company_name, len(raw_jobs))

    return [_normalise(j, company_name) for j in raw_jobs]
