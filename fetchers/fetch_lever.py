"""Lever ATS fetcher.

Endpoint: GET https://api.lever.co/v0/postings/{slug}?mode=json
No auth required. Returns a flat JSON array of postings.

Response shape (per posting):
  { "text" (title), "hostedUrl", "applyUrl", "createdAt" (ms),
    "categories": { "commitment", "location", "team", "department",
                    "allLocations": [] },
    "description" (HTML), "descriptionPlain",
    "additional" (HTML), "additionalPlain",
    "lists": [ {"text", "content"} ],
    "workplaceType": "remote" | "on-site" | "hybrid" }

The `categories.commitment` field reliably indicates employment type:
  "Full-time", "Part-time", "Internship", "Contract"
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.lever.co/v0/postings"


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:2000]


def _normalise(posting: dict, company_name: str) -> dict:
    """Map Lever posting → common schema."""
    cats = posting.get("categories") or {}
    location = cats.get("location", "")
    all_locs = cats.get("allLocations", [])
    if all_locs:
        location = " | ".join(all_locs)

    desc_plain = posting.get("descriptionPlain", "")
    desc_html = posting.get("description", "")
    description = desc_plain[:2000] if desc_plain else _strip_html(desc_html)

    commitment = cats.get("commitment", "")
    team = cats.get("team", "")
    department = cats.get("department", "")
    departments = ", ".join(filter(None, [department, team]))

    return {
        "company": company_name,
        "title": posting.get("text", ""),
        "location": location,
        "employment_type": commitment or "Unknown",
        "description": description,
        "apply_url": posting.get("hostedUrl", "") or posting.get("applyUrl", ""),
        "ats_source": "Lever",
        "departments": departments,
        "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


async def fetch_lever(
    client: httpx.AsyncClient,
    slug: str,
    company_name: str,
) -> list[dict]:
    """Fetch all postings from a Lever job board.

    Args:
        client: Shared httpx async client.
        slug: Lever board slug (path segment in jobs.lever.co/{slug}).
        company_name: Human-readable company name for output.

    Returns:
        List of normalised job dicts.
    """
    all_postings: list[dict] = []
    offset = 0
    limit = 100

    while True:
        url = f"{API_BASE}/{slug}"
        params = {"mode": "json", "limit": limit, "skip": offset}

        try:
            resp = await client.get(url, params=params, timeout=30)
            if resp.status_code == 404:
                logger.warning(
                    "[Lever/%s] 404 — slug '%s' not found (company may have "
                    "migrated off Lever)",
                    company_name, slug,
                )
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[Lever/%s] HTTP %s — %s",
                company_name, exc.response.status_code, exc,
            )
            return all_postings
        except httpx.RequestError as exc:
            logger.warning("[Lever/%s] request error: %s", company_name, exc)
            return all_postings

        batch = resp.json()
        if not isinstance(batch, list) or len(batch) == 0:
            break

        all_postings.extend(batch)
        logger.debug(
            "[Lever/%s] page offset=%d → %d postings", company_name, offset, len(batch)
        )

        if len(batch) < limit:
            break
        offset += limit

    logger.info("[Lever/%s] fetched %d total postings", company_name, len(all_postings))
    return [_normalise(p, company_name) for p in all_postings]
