import pytest
from fastapi.testclient import TestClient

from jobfinder import agent, db, server
from test_agent import FakeClient, _job, reply


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("k1", salary_min_lpa=14, salary_max_lpa=16), _job("k2")],
                   "2026-10-12T00:00:00Z")
    conn.close()
    return TestClient(server.app)


def test_answer_jobs_come_from_the_database_in_the_agents_order(api, monkeypatch):
    fake = FakeClient(reply(("search_jobs", {"description_words": "kubernetes"})),
                      reply(("give_answer", {"answer": "Both.", "job_ids": ["k2", "k1"]})))
    monkeypatch.setattr(agent, "make_client", lambda: fake)
    body = api.post("/api/ask", json={"question": "kubernetes internships?"}).json()
    assert (body["answer"], body["stopped"]) == ("Both.", "answered")
    assert [j["id"] for j in body["jobs"]] == ["k2", "k1"]
    # Shaped like /api/jobs rows, with pay read from the database, not from the model.
    assert body["jobs"][1]["salary_max_lpa"] == 16
    # "pick" only chooses a group's representative row inside find_jobs; the app never reads it.
    assert set(api.get("/api/jobs").json()["jobs"][0]) - {"pick"} <= set(body["jobs"][0])
    assert [s["kind"] for s in body["steps"]] == ["model", "tool", "model", "answer"]


def test_a_question_must_have_some_length(api):
    assert api.post("/api/ask", json={"question": "hi"}).status_code == 422


def test_no_key_is_a_clear_error_not_a_crash(api, monkeypatch):
    monkeypatch.setenv("OMNIROUTE_API_KEY", "")
    response = api.post("/api/ask", json={"question": "anything remote?"})
    assert response.status_code == 503
    assert "OMNIROUTE_API_KEY" in response.json()["detail"]
