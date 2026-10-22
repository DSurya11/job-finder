"""Adapter for johnvc/wellfound-jobs-api dataset rows.

The configured crawlerbros Wellfound actor 404s. This module maps the live
actor's nested company and location fields onto job_finder.py's existing keys.
"""

from __future__ import annotations

from typing import Any

WELLFOUND_ACTOR_ID = "johnvc/wellfound-jobs-api"
WELLFOUND_ACTOR_URL = "https://apify.com/johnvc/wellfound-jobs-api"
DESCRIPTION_CAP = 700


def _as_text(value: Any) -> str:
    """Return a stripped string, ignoring nested objects."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _company_name(raw: dict[str, Any]) -> str:
    """Read company from a nested object or a flat string field."""
    company = raw.get("company")
    if isinstance(company, dict):
        return _as_text(company.get("name"))
    name = _as_text(company)
    if name:
        return name
    for key in ("companyName", "startupName", "organizationName"):
        text = _as_text(raw.get(key))
        if text:
            return text
    return ""


def _location(raw: dict[str, Any]) -> str:
    """Prefer locationNames, then remote, then a flat location field."""
    names = raw.get("locationNames")
    if isinstance(names, list):
        joined = ", ".join(_as_text(item) for item in names if _as_text(item))
        if joined:
            return joined
    if raw.get("remote") is True:
        return "Remote"
    ctx = raw.get("searchContext")
    if isinstance(ctx, dict):
        ctx_loc = _as_text(ctx.get("location"))
        if ctx_loc:
            return ctx_loc
    for key in ("location", "jobLocation"):
        text = _as_text(raw.get(key))
        if text:
            return text
    return ""


def _salary(raw: dict[str, Any]) -> str:
    """Prefer the actor's compensation text, then min/max salary."""
    text = _as_text(raw.get("compensationRaw"))
    if text:
        return text
    lo = raw.get("salaryMin")
    hi = raw.get("salaryMax")
    if lo or hi:
        return f"{lo or '?'}-{hi or '?'}"
    for key in ("compensation", "salary", "equity", "salaryRange"):
        text = _as_text(raw.get(key))
        if text:
            return text
    return ""


def _url(raw: dict[str, Any], fallback: str = "") -> str:
    """Return the job URL, then an optional scanner fallback."""
    for key in ("url", "jobUrl", "link", "applyUrl"):
        text = _as_text(raw.get(key))
        if text.startswith("http"):
            return text
    return fallback


def normalize_wellfound_row(raw: dict[str, Any], *, url_fallback: str = "") -> dict[str, str]:
    """Map one actor row onto job_finder.py's existing Wellfound keys.

    Args:
        raw: One dataset item from ``johnvc/wellfound-jobs-api``.
        url_fallback: Value from the caller's URL scanner when the row has none.

    Returns:
        The same keys the Wellfound normalizer already stored.
    """
    description = _as_text(raw.get("description")) or _as_text(raw.get("jobDescription")) or _as_text(raw.get("about"))
    return {
        "title": _as_text(raw.get("title"))
        or _as_text(raw.get("primaryRoleTitle"))
        or _as_text(raw.get("jobTitle"))
        or _as_text(raw.get("role")),
        "company": _company_name(raw),
        "location": _location(raw),
        "salary": _salary(raw),
        "url": _url(raw, fallback=url_fallback),
        "description": description[:DESCRIPTION_CAP],
        "source": "Wellfound",
        "posted": _as_text(raw.get("postedAt"))
        or _as_text(raw.get("createdAt"))
        or _as_text(raw.get("date")),
    }
