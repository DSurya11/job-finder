from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from jobfinder import db, pipeline, server


def _ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job(job_id: str, source: str = "greenhouse") -> dict:
    return {"id": job_id, "company": "Acme", "title": f"Engineer {job_id}", "location": "Pune",
            "cities": ["Pune"], "level": "Entry", "role": "Backend", "is_tech": 1,
            "employment_type": "Full-time", "description": "", "salary_text": "",
            "apply_url": f"https://example.com/{job_id}", "source": source,
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    return db.connect()


def _state(conn, job_id: str, status: str, notes: str = "") -> None:
    conn.execute("INSERT INTO user_state (job_id, status, notes, updated_at) VALUES (?,?,?,?)",
                 (job_id, status, notes, db.now()))


def _close(conn, job_id: str, days_ago: float) -> None:
    conn.execute("UPDATE jobs SET is_active = 0, closed_at = ? WHERE id = ?", (_ago(days_ago), job_id))


def _ids(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT id FROM jobs")}


def test_closing_records_when_and_coming_back_reopens(conn):
    db.upsert_jobs(conn, [_job("a")], _ago(2))
    assert db.close_missing(conn, "Acme", _ago(1)) == 1
    is_active, closed_at = conn.execute("SELECT is_active, closed_at FROM jobs WHERE id='a'").fetchone()
    assert (is_active, closed_at[:10]) == (0, _ago(1)[:10])
    db.upsert_jobs(conn, [_job("a")], _ago(0))              # seen again within the grace period
    assert tuple(conn.execute("SELECT is_active, closed_at FROM jobs WHERE id='a'").fetchone()) == (1, None)


def test_only_untracked_jobs_past_their_grace_period_are_deleted(conn):
    names = ["untouched_old", "untouched_recent", "aggregator_today", "dismissed_old",
             "saved_old", "applied_old", "note_only_old", "open"]
    db.upsert_jobs(conn, [_job(n, "linkedin" if n.startswith("aggregator") else "greenhouse")
                          for n in names], _ago(30))
    for name, days in [("untouched_old", 10), ("untouched_recent", 2), ("aggregator_today", 0),
                       ("dismissed_old", 10), ("saved_old", 10), ("applied_old", 10),
                       ("note_only_old", 10)]:
        _close(conn, name, days)
    _state(conn, "dismissed_old", "hidden")
    _state(conn, "saved_old", "saved")
    _state(conn, "applied_old", "applied")
    _state(conn, "note_only_old", "", notes="ask about the team")

    deleted = db.purge_closed(conn, pipeline.AGGREGATORS, pipeline.CLOSED_GRACE_DAYS)

    assert deleted == 3
    assert _ids(conn) == {"untouched_recent", "saved_old", "applied_old", "note_only_old", "open"}
    # The dismissal outlives the row, so a repost of the same posting stays dismissed.
    assert tuple(conn.execute("SELECT status FROM user_state WHERE job_id='dismissed_old'").fetchone()) == ("hidden",)


def test_jobs_closed_before_this_change_get_their_last_seen_as_closed_at(tmp_path, monkeypatch, conn):
    db.upsert_jobs(conn, [_job("old")], _ago(20))
    conn.execute("UPDATE jobs SET is_active = 0, closed_at = NULL")
    conn.commit()
    db._READY.discard(str(db.DB_PATH))                      # connect() runs its checks again
    fresh = db.connect()
    assert fresh.execute("SELECT closed_at FROM jobs").fetchone()[0][:10] == _ago(20)[:10]


def test_a_closed_application_stays_in_its_tab_and_leaves_everything_else(conn):
    db.upsert_jobs(conn, [_job("applied"), _job("open")], _ago(1))
    _state(conn, "applied", "applied")
    _close(conn, "applied", 3)
    conn.commit()
    api = TestClient(server.app)

    tab = api.get("/api/jobs", params={"status": "applied"}).json()["jobs"]
    assert [(j["id"], j["is_active"]) for j in tab] == [("applied", False)]
    assert [j["id"] for j in api.get("/api/jobs").json()["jobs"]] == ["open"]
    assert api.get("/api/facets").json()["tracker"] == {"applied": 1}
