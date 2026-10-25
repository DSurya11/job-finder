import sqlite3

import pytest
from fastapi.testclient import TestClient

from jobfinder import db, enrich, server


def _job(job_id: str, title: str, company: str = "Microsoft", level: str = "Mid") -> dict:
    return {"id": job_id, "company": company, "title": title, "location": "Hyderabad",
            "cities": ["Hyderabad"], "level": level, "role": "Software Engineering", "is_tech": 1,
            "employment_type": "Full-time", "description": "", "salary_text": "",
            "apply_url": f"https://example.com/{job_id}", "source": "greenhouse",
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}


@pytest.mark.parametrize("a, b", [
    # Pairs from the October 2026 data that were two rows.
    (("Microsoft", "Software Engineer II"), ("Microsoft", "Software Engineer-II")),
    (("Palo Alto Networks", "Sr Professional Services Engineer"),
     ("Palo Alto Networks", "Sr. Professional Services Engineer")),
    (("NEC Software Solutions", "Software Engineer - Full Stack"),
     ("NEC Software Solutions (India)", "Software Engineer - Full Stack")),
])
def test_punctuation_and_company_suffixes_do_not_split_a_job(a, b):
    assert enrich.group_key(*a, "Mid") == enrich.group_key(*b, "Mid")


def test_c_cpp_and_csharp_stay_apart():
    keys = {enrich.group_key("X", t, "Entry") for t in ("C Developer", "C++ Developer", "C# Developer")}
    assert len(keys) == 3


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("a", "Software Engineer II"), _job("b", "Software Engineer-II"),
                          _job("c", "Software Engineer III")], "2026-10-24T00:00:00Z")
    conn.close()
    return TestClient(server.app)


def test_the_table_shows_variants_as_one_row(api):
    body = api.get("/api/jobs", params={"tech": True}).json()
    assert body["total"] == 2
    assert sorted(j["openings"] for j in body["jobs"]) == [1, 2]
    others = api.get("/api/jobs/a").json()["others"]
    assert [o["id"] for o in others] == ["b"]


def test_dismissing_a_row_dismisses_its_variants(api):
    api.put("/api/jobs/a/state", json={"status": "hidden"})
    assert [j["id"] for j in api.get("/api/jobs").json()["jobs"]] == ["c"]


def test_an_old_database_with_the_generated_column_is_converted(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA)
    old.execute("INSERT INTO jobs (id, company, title, level, is_active) VALUES "
                "('x', 'Microsoft', 'Software Engineer-II', 'Mid', 1)")
    old.execute("ALTER TABLE jobs ADD COLUMN grp TEXT GENERATED ALWAYS AS "
                "(company || '|' || lower(title) || '|' || level) VIRTUAL")
    old.execute("CREATE INDEX idx_jobs_grp ON jobs(is_active, grp)")
    old.commit()
    old.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = db.connect()
    assert conn.execute("SELECT grp FROM jobs").fetchone()[0] == enrich.group_key(
        "Microsoft", "Software Engineer II", "Mid")
    hidden = {r["name"]: r["hidden"] for r in conn.execute("PRAGMA table_xinfo(jobs)")}["grp"]
    assert hidden == 0                                   # a plain stored column now
