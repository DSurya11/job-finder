"""Offline fixture tests for the Wellfound Apify adapter.

These tests do not call Apify.
"""

from __future__ import annotations

from jobfinder.wellfound_apify import WELLFOUND_ACTOR_ID, normalize_wellfound_row

# Trimmed johnvc/wellfound-jobs-api row. No profile or contact fields.
JOHNVC_ROW = {
    "title": "Software Engineer Intern",
    "primaryRoleTitle": "Software Engineer Intern",
    "url": "https://wellfound.com/jobs/example-intern",
    "description": "Internship on the backend team in India.",
    "postedAt": "2026-10-01T00:00:00Z",
    "remote": True,
    "locationNames": ["India", "Remote"],
    "salaryMin": 0,
    "salaryMax": 0,
    "compensationRaw": "Equity listed",
    "company": {
        "name": "Example Startup",
        "slug": "example-startup",
        "url": "https://wellfound.com/company/example-startup",
    },
}

FLAT_ROW = {
    "jobTitle": "Python Intern",
    "companyName": "Flat Co",
    "location": "Bengaluru",
    "jobUrl": "https://wellfound.com/jobs/flat",
    "jobDescription": "Write tests.",
    "postedAt": "2026-09-15",
}


def test_actor_id_is_the_live_wellfound_actor() -> None:
    assert WELLFOUND_ACTOR_ID == "johnvc/wellfound-jobs-api"
    assert "crawlerbros" not in WELLFOUND_ACTOR_ID


def test_nested_company_and_location_names() -> None:
    out = normalize_wellfound_row(JOHNVC_ROW)
    assert out["title"] == "Software Engineer Intern"
    assert out["company"] == "Example Startup"
    assert out["location"] == "India, Remote"
    assert out["url"] == "https://wellfound.com/jobs/example-intern"
    assert out["description"].startswith("Internship")
    assert out["posted"] == "2026-10-01T00:00:00Z"
    assert out["source"] == "Wellfound"
    assert out["salary"] == "Equity listed"
    assert "{" not in out["company"]


def test_flat_row_still_maps() -> None:
    out = normalize_wellfound_row(FLAT_ROW)
    assert out["title"] == "Python Intern"
    assert out["company"] == "Flat Co"
    assert out["location"] == "Bengaluru"
    assert out["url"] == "https://wellfound.com/jobs/flat"
    assert out["description"] == "Write tests."
    assert out["posted"] == "2026-09-15"


def test_url_fallback_when_row_has_none() -> None:
    out = normalize_wellfound_row(
        {"title": "Intern", "companyName": "X"},
        url_fallback="https://wellfound.com/jobs/fallback",
    )
    assert out["url"] == "https://wellfound.com/jobs/fallback"
