import json

import pytest

from jobfinder import agent_tools as tools
from jobfinder import db


def _job(job_id: str, **kw) -> dict:
    base = {"id": job_id, "company": "Acme", "title": f"Engineer {job_id}", "location": "Bengaluru",
            "cities": ["Bengaluru"], "level": "Entry", "role": "DevOps / SRE", "is_tech": 1,
            "employment_type": "Full-time", "description": "Kubernetes and Terraform.",
            "salary_text": "", "apply_url": f"https://example.com/{job_id}", "source": "greenhouse",
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}
    return {**base, **kw}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [
        _job("blr"),
        _job("ncr", cities=["Delhi NCR"], location="Gurugram", role="Backend"),
        *[_job(f"many{i}", title=f"Role {i}") for i in range(25)],
    ], "2026-10-24T00:00:00Z")
    return conn


def test_usual_city_spellings_are_understood(conn):
    found = json.loads(tools.search_jobs(conn, cities=["Gurgaon"]))
    assert [j["id"] for j in found["jobs"]] == ["ncr"]


def test_unknown_values_are_errors_that_list_what_works(conn):
    with pytest.raises(tools.ToolError, match=r"unknown levels \['Junior'\].*'Entry'"):
        tools.search_jobs(conn, levels=["Junior"])
    with pytest.raises(tools.ToolError, match="Cities with jobs: .*Bengaluru"):
        tools.search_jobs(conn, cities=["Atlantis"])
    with pytest.raises(tools.ToolError, match="no job with id 'nope'"):
        tools.get_job_details(conn, job_id="nope")


def test_rows_are_capped_and_say_how_many_more_match(conn):
    found = json.loads(tools.search_jobs(conn, limit=500))
    assert found["showing"] == tools.MAX_ROWS
    assert found["total_matching"] == 27
    assert "7 more match" in found["note"]
    assert "description" not in found["jobs"][0]           # short rows only


def test_schema_offers_only_values_in_the_data(conn):
    search = tools.schemas(conn)[0]["function"]["parameters"]["properties"]
    assert search["roles"]["items"]["enum"] == ["Backend", "DevOps / SRE"]


def test_profile_leaves_personal_details_out(profile_file, conn):
    text = tools.get_my_profile(conn)
    assert json.loads(text)["target_pay_lpa"] == 12     # the test profile, not the real one
    assert json.loads(text)["skills"] == {"primary": ["Python"]}
    for secret in ("Test Person", "test@example.com", "99999"):
        assert secret not in text
