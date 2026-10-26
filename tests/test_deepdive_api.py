"""The deep-dive endpoints: start in the background, report state, refuse unknown jobs."""

import time

from fastapi.testclient import TestClient

from jobfinder import db, deepdive, server


def test_start_then_poll_until_the_report_is_there(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [{"id": "j1", "company": "Acme", "title": "SRE", "location": "Pune", "cities": ["Pune"],
                           "level": "Entry", "role": "DevOps / SRE", "is_tech": 1, "employment_type": "Full-time",
                           "description": "x", "salary_text": "", "apply_url": "https://acme.com/1",
                           "source": "greenhouse", "pay_verdict": "unknown", "score": 50, "score_reasons": []}],
                   "2026-10-24T00:00:00Z")

    def fake_research(job_id):
        report = deepdive.Report(job_id=job_id, stopped="answered",
                                 report={"strengths": [], "gaps": [], "bullets": [], "company": [], "message": ""})
        deepdive.save(db.connect(), report)
        return report
    monkeypatch.setattr(deepdive, "research", fake_research)
    monkeypatch.setattr(server, "DEEP_DIVES", {})
    client = TestClient(server.app)
    assert client.get("/api/jobs/j1/deepdive").json() == {"running": False, "error": None, "deepdive": None}
    assert client.post("/api/jobs/j1/deepdive").json() == {"started": True}
    for _ in range(50):
        state = client.get("/api/jobs/j1/deepdive").json()
        if state["deepdive"]:
            break
        time.sleep(0.05)
    assert state["running"] is False and state["deepdive"]["report"]["strengths"] == []
    assert client.post("/api/jobs/nope/deepdive").status_code == 404
