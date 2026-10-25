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


def test_an_empty_search_counts_what_each_filter_costs(conn):
    found = json.loads(tools.search_jobs(conn, cities=["Gurgaon"], roles=["DevOps / SRE"]))
    assert found["total_matching"] == 0
    # The only Gurgaon job is Backend; the DevOps jobs are all in Bengaluru.
    assert found["if_you_drop"] == {"roles": 1, "cities": 26, "hide_low_pay": 0, "tech_only": 0}
    one_filter = json.loads(tools.search_jobs(conn, cities=["Chennai"], hide_low_pay=False, tech_only=False))
    assert "if_you_drop" not in one_filter                  # nothing to compare with one filter


def test_fit_rounds_like_the_table_and_pay_says_what_kind_it_is(conn):
    db.upsert_jobs(conn, [_job("half", score=48.5, est_min_lpa=26.1, est_max_lpa=38.7,
                               est_source="market")], "2026-10-24T00:00:00Z")
    job = json.loads(tools.get_job_details(conn, job_id="half"))
    assert job["fit_score"] == 49                  # Python's round(48.5) is 48; the table shows 49
    assert "NOT this company's pay" in job["pay"]


def test_schema_offers_only_values_in_the_data(conn):
    search = tools.schemas(conn)[0]["function"]["parameters"]["properties"]
    assert search["roles"]["items"]["enum"] == ["Backend", "DevOps / SRE"]


def test_profile_comes_in_parts_and_leaves_personal_details_out(profile_file, conn):
    pay = json.loads(tools.get_my_profile(conn, part="pay_floor"))
    assert pay["target_pay_lpa"] == 12                   # the test profile, not the real one
    assert "looking_for" not in pay                       # the pay floor alone: no job type
    assert json.loads(tools.get_my_profile(conn, part="skills"))["skills"] == {"primary": ["Python"]}
    assert json.loads(tools.get_my_profile(conn, part="preferences"))["looking_for"] == "full-time"
    for part in tools.PROFILE_PARTS:
        text = tools.get_my_profile(conn, part=part)
        for secret in ("Test Person", "test@example.com", "99999"):
            assert secret not in text
    with pytest.raises(tools.ToolError, match="unknown part"):
        tools.get_my_profile(conn, part="everything")


def test_an_empty_date_search_says_how_old_the_data_is(conn):
    conn.execute("UPDATE jobs SET posted_at = '', first_seen = '2026-09-01T08:00:00Z'")
    found = json.loads(tools.search_jobs(conn, posted_within_days=7))
    assert found["total_matching"] == 0
    assert found["newest_posting_in_data"] == "2026-09-01"


def test_a_description_filter_that_cuts_most_matches_is_counted(conn):
    # Measured: "machine learning internships" became role ML / AI plus description_any
    # ["machine learning"], and the answer said 16 when 56 matched the role.
    db.upsert_jobs(conn, [_job(f"helm{i}", description="Helm charts on EKS.") for i in range(2)],
                   "2026-10-24T00:00:00Z")
    found = json.loads(tools.search_jobs(conn, roles=["DevOps / SRE"], description_any=["helm"]))
    assert found["total_matching"] == 2
    assert found["without_description_filter"] == 28
    assert "cut 28 matches to 2" in found["note"]
    most = json.loads(tools.search_jobs(conn, roles=["DevOps / SRE"], description_words="kubernetes"))
    assert "without_description_filter" not in most          # it barely narrowed: no note
