import time

import pytest
from fastapi.testclient import TestClient

from jobfinder import db, pipeline, server


def _job(job_id: str, top_lpa: float) -> dict:
    return {"id": job_id, "company": "Acme", "title": f"Engineer {job_id}", "location": "Pune",
            "cities": ["Pune"], "level": "Entry", "role": "Backend", "is_tech": 1,
            "employment_type": "Full-time", "description": "", "salary_text": f"{top_lpa} LPA",
            "salary_min_lpa": top_lpa, "salary_max_lpa": top_lpa,
            "apply_url": f"https://example.com/{job_id}", "source": "greenhouse",
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}


@pytest.fixture
def api(tmp_path, monkeypatch, profile_file):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("ten", 10), _job("fifteen", 15)], "2026-10-24T00:00:00Z")
    pipeline.rescore(conn)
    conn.close()
    return TestClient(server.app)


def _wait_for_rescore(timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while pipeline.PROGRESS["running"]:
        assert time.monotonic() < deadline, "the background re-score did not finish"
        time.sleep(0.02)


def _verdicts() -> dict:
    conn = db.connect()
    try:
        return {r["id"]: r["pay_verdict"] for r in conn.execute("SELECT id, pay_verdict FROM jobs")}
    finally:
        conn.close()


def test_saving_the_floors_rescores_every_job(api):
    assert api.get("/api/settings/pay").json() == {"min_lpa": 9, "target_lpa": 12}
    assert _verdicts() == {"ten": "ok", "fifteen": "target"}

    saved = api.put("/api/settings/pay", json={"min_lpa": 12, "target_lpa": 18}).json()
    assert saved == {"min_lpa": 12, "target_lpa": 18, "rescoring": True}   # answers at once
    _wait_for_rescore()

    assert pipeline.PROGRESS["done"] == pipeline.PROGRESS["total"] == 2
    assert _verdicts() == {"ten": "low", "fifteen": "ok"}
    assert api.get("/api/settings/pay").json() == {"min_lpa": 12, "target_lpa": 18}


def test_saving_keeps_the_rest_of_the_profile_and_its_comments(api, profile_file):
    before = profile_file.read_text(encoding="utf-8")
    api.put("/api/settings/pay", json={"min_lpa": 12.5, "target_lpa": 18})
    _wait_for_rescore()
    after = profile_file.read_text(encoding="utf-8")
    assert "  min_lpa: 12.5                     # below this a full-time job is marked low pay" in after
    assert "  target_lpa: 18                 # what you are aiming for" in after
    changed = [(b, a) for b, a in zip(before.splitlines(), after.splitlines()) if b != a]
    assert len(changed) == 2 and len(before.splitlines()) == len(after.splitlines())


@pytest.mark.parametrize("body", [
    {"min_lpa": 20, "target_lpa": 18},       # minimum above target
    {"min_lpa": 0, "target_lpa": 18},
    {"min_lpa": 12, "target_lpa": 900},
])
def test_impossible_floors_are_refused_and_nothing_changes(api, profile_file, body):
    before = profile_file.read_text(encoding="utf-8")
    assert api.put("/api/settings/pay", json=body).status_code == 400
    assert profile_file.read_text(encoding="utf-8") == before


def test_no_saving_while_a_refresh_runs(api, monkeypatch):
    monkeypatch.setitem(pipeline.PROGRESS, "running", True)
    assert api.put("/api/settings/pay", json={"min_lpa": 12, "target_lpa": 18}).status_code == 409
    assert _verdicts() == {"ten": "ok", "fifteen": "target"}
