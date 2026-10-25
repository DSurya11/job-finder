"""The eval checker against scripted runs: each broken run must fail its check, and only that."""

import pytest

from jobfinder import agent, evals
from test_agent import FakeClient, _job, reply
from jobfinder import db

CASE = {"id": "k", "question": "kubernetes internships", "filters": {"description_words": "kubernetes"},
        "not_filters": ["min_pay_lpa", "levels"], "picks_match": True, "states_total": True}
GOOD = "There are 2 jobs that mention Kubernetes in your database."


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("k1"), _job("k2", title="SRE intern"),
                          _job("other", description="Java only.")], "2026-10-12T00:00:00Z")
    return conn


def _checks(conn, search: dict, answer: str, ids: list[str]) -> dict:
    fake = FakeClient(reply(("search_jobs", search)), reply(("give_answer", {"answer": answer, "job_ids": ids})))
    return evals.check_run(conn, CASE, agent.ask(CASE["question"], conn=conn, client=fake))


def _failed(checks: dict) -> list[str]:
    return [name for name, ok in checks.items() if not ok]


def test_a_good_run_passes_everything(conn):
    assert _failed(_checks(conn, {"description_words": "Kubernetes"}, GOOD, ["k1"])) == []


@pytest.mark.parametrize("search, answer, ids, fails", [
    # A filter nobody asked for, which here happens not to change the result.
    ({"description_words": "kubernetes", "levels": ["Intern"]}, GOOD, ["k1"], ["not_filters"]),
    ({"description_words": "docker"}, GOOD, [], ["filters", "picks_match"]),
    ({"description_words": "kubernetes"}, "There are 5 jobs that mention Kubernetes.", ["k1"], ["states_total"]),
    ({"description_words": "kubernetes"}, "Hay 2 ofertas de trabajo con Kubernetes.", ["k1"], ["english"]),
    ({"description_words": "kubernetes"}, GOOD + " Remove min_pay_lpa to see more.", ["k1"], ["no_internal_names"]),
    ({"description_words": "kubernetes"}, GOOD, ["k1", "other"], ["picks_match"]),
])
def test_each_mistake_fails_its_check(conn, search, answer, ids, fails):
    # "other" was returned by no search here, so the agent's own ID check drops it before
    # the eval sees it; search for everything first so it is a real, but wrong, pick.
    if "other" in ids:
        search = {**search}
        fake = FakeClient(reply(("search_jobs", {})), reply(("search_jobs", search)),
                          reply(("give_answer", {"answer": answer, "job_ids": ids})))
        checks = evals.check_run(conn, CASE, agent.ask(CASE["question"], conn=conn, client=fake))
    else:
        checks = _checks(conn, search, answer, ids)
    assert sorted(_failed(checks)) == sorted(fails)


def test_one_word_of_any_counts_as_that_word(conn):
    checks = _checks(conn, {"description_any": ["Kubernetes"]}, GOOD, ["k1"])
    assert _failed(checks) == []
