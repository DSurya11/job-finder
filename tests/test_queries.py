from jobfinder import db, queries


def _job(job_id: str, description: str, **kw) -> dict:
    base = {"id": job_id, "company": "Acme", "title": f"Engineer {job_id}", "location": "Pune",
            "cities": ["Pune"], "level": "Entry", "role": "DevOps / SRE", "is_tech": 1,
            "employment_type": "Full-time", "description": description, "salary_text": "",
            "apply_url": f"https://example.com/{job_id}", "source": "greenhouse",
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}
    return {**base, **kw}


NO_FILTERS = dict(q=None, role=None, level=None, etype=None, city=None, company=None, source=None,
                  status=None, remote=False, tech=False, salary_min=None, exp_max=None,
                  has_salary=False, new_days=None, pay_filter=None, hide_bad=False,
                  min_score=None, has_description=False)


def _ids(conn, **filters) -> set[str]:
    where, args = queries.build_where(**{**NO_FILTERS, **filters})
    _, rows = queries.find_jobs(conn, where, args, None, "score", None, 1, 50)
    return {r["id"] for r in rows}


def _conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [
        _job("k8s", "We run Kubernetes and Kafka in production."),
        _job("uber", "Experience at Uber or a similar marketplace."),
        _job("python", "Python and Kafka streaming."),
        _job("blank", ""),
    ], "2026-10-24T00:00:00Z")
    return conn


def test_description_words_match_from_the_start_of_a_word(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    assert _ids(conn, desc="kube") == {"k8s"}
    assert _ids(conn, desc="KUBERNETES") == {"k8s"}          # case does not matter
    # "uber" sits inside "Kubernetes" but does not start a word there.
    assert _ids(conn, desc="uber") == {"uber"}


def test_every_description_word_must_appear(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    assert _ids(conn, desc="kafka") == {"k8s", "python"}
    assert _ids(conn, desc="kafka python") == {"python"}
    assert _ids(conn, desc="   ") == {"k8s", "uber", "python", "blank"}   # only spaces: no filter


def test_description_filter_combines_with_the_others(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    # "streaming" is only in a description: the search box (q) never looks there, desc does.
    assert _ids(conn, q="streaming") == set()
    assert _ids(conn, desc="streaming") == {"python"}
    assert _ids(conn, desc="kafka", role="Backend") == set()
