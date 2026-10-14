import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from jobfinder import db, pipeline, server


def _ago(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job(job_id: str, **kw) -> dict:
    base = {"id": job_id, "company": "Acme", "title": f"Engineer {job_id}", "location": "Pune",
            "cities": ["Pune"], "level": "Entry", "role": "Backend", "is_tech": 1,
            "employment_type": "Full-time", "description": "", "salary_text": "",
            "apply_url": f"https://example.com/{job_id}", "source": "greenhouse",
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}
    return {**base, **kw}


@pytest.fixture
def api(tmp_path, monkeypatch):
    """The app on a new database: one job first seen 2 hours ago, one just over a day ago."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("fresh")], _ago(hours=2))
    db.upsert_jobs(conn, [_job("older")], _ago(hours=24, minutes=5))
    conn.close()
    return TestClient(server.app)


def test_new_means_the_last_24_hours(api):
    # The older job falls on the same date as the 24-hour cutoff, a little before it.
    # Compared as text against SQLite's "YYYY-MM-DD HH:MM:SS", everything on that date
    # counted as new, because the "T" in a stored timestamp sorts after the space.
    assert [j["id"] for j in api.get("/api/jobs", params={"new_days": 1}).json()["jobs"]] == ["fresh"]
    counts = api.get("/api/facets").json()
    assert counts["rows"] == {"all": 2, "new": 1}
    assert counts["totals"]["new_today"] == 1


def test_first_seen_filter_narrows_the_all_count(api):
    assert api.get("/api/facets", params={"new_days": 1}).json()["rows"] == {"all": 1, "new": 1}
    assert api.get("/api/facets", params={"new_days": 3}).json()["rows"] == {"all": 2, "new": 1}


def test_search_of_only_spaces(api):
    assert api.get("/api/jobs", params={"q": "   "}).json()["total"] == 2


def test_unknown_job_and_unknown_api_path(api):
    assert api.get("/api/jobs/nope").status_code == 404
    assert api.put("/api/jobs/nope/state", json={"status": "saved"}).status_code == 404
    assert api.get("/api/nope").status_code == 404


def test_a_note_outlives_its_status(api):
    def state():
        job = api.get("/api/jobs/fresh").json()
        return job["status"], job["notes"]

    api.put("/api/jobs/fresh/state", json={"notes": "ask Asha for a referral"})
    assert state() == ("saved", "ask Asha for a referral")          # a first note shortlists
    api.put("/api/jobs/fresh/state", json={"status": ""})
    assert state() == ("", "ask Asha for a referral")               # un-shortlisted, note kept
    assert api.get("/api/facets").json()["tracker"] == {}
    api.put("/api/jobs/fresh/state", json={"notes": "asked"})
    assert state() == ("", "asked")                                 # and editing it does not re-shortlist
    api.put("/api/jobs/fresh/state", json={"status": "", "notes": ""})
    assert state() == (None, None)


def test_coverage_keeps_companies_a_partial_run_skipped(api, monkeypatch):
    monkeypatch.setattr(pipeline, "load_companies", lambda path=None: [{"name": "Acme"}, {"name": "Globex"}])
    conn = db.connect()
    conn.execute("INSERT INTO runs (id, started, finished) VALUES (1, 'a', 'b'), (2, 'c', NULL)")
    conn.executemany("INSERT INTO company_runs VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, "Acme", "greenhouse", 1, 40, 12, "", 1.0, "a"),
        (1, "Globex", "lever", 1, 9, 9, "", 1.0, "a"),
        (1, "Dropped Co", "lever", 1, 5, 5, "", 1.0, "a"),      # since taken off companies.yaml
        (2, "Acme", "greenhouse", 1, 40, 3, "", 1.0, "c"),      # run 2 fetched Acme only, and was cut short
    ])
    conn.commit()
    conn.close()
    report = api.get("/api/coverage").json()
    assert {c["company"]: (c["india"], c["previous"], c["status"]) for c in report["companies"]} == {
        "Acme": (3, 12, "dropped"), "Globex": (9, None, "ok"),
    }
    assert report["summary"] == {"dropped": 1, "ok": 1}


def test_a_run_that_dies_does_not_stay_in_progress(monkeypatch):
    async def dies(companies, with_details):
        pipeline.PROGRESS.update(running=True, current="job descriptions")
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "_run", dies)
    with pytest.raises(RuntimeError):
        asyncio.run(pipeline.run())
    assert pipeline.PROGRESS["running"] is False and pipeline.PROGRESS["current"] == ""
