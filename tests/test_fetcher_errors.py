"""A source that fails must show as failed, and must not close its open jobs.

Found 2026-10-26: Swiggy's careers host answered 402 every day and the fetcher returned an
empty list, so Coverage said "listed nothing". Goldman Sachs and Amazon returned the pages read
before an error, the run counted as complete, and the jobs on the missing pages were closed.
"""

import asyncio

import httpx
import pytest

from fetchers import fetch_amazon, fetch_eightfold, fetch_gs, fetch_swiggy
from jobfinder import db, pipeline


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_swiggy_raises_the_http_error_instead_of_an_empty_list():
    async def go():
        async with client(lambda r: httpx.Response(402)) as c:
            await fetch_swiggy.fetch_swiggy_jobs(c, {"name": "Swiggy"})
    with pytest.raises(httpx.HTTPStatusError, match="402"):
        asyncio.run(go())


def test_eightfold_raises_on_an_error_status():
    async def go():
        async with client(lambda r: httpx.Response(500)) as c:
            await fetch_eightfold.fetch_eightfold(c, "Morgan Stanley", "morganstanley")
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(go())


def test_amazon_raises_when_a_later_page_fails_instead_of_returning_part(monkeypatch):
    monkeypatch.setattr(fetch_amazon, "MAX_RETRIES", 2)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(fetch_amazon.asyncio, "sleep", lambda *_: real_sleep(0))
    job = {"title": "SDE", "normalized_location": "Bengaluru", "url_next_step": "https://x", "id_icims": "1"}

    def handler(request):
        if "offset=0" in str(request.url):
            return httpx.Response(200, json={"jobs": [job] * fetch_amazon.PAGE_SIZE, "hits": 500})
        return httpx.Response(503)

    async def go():
        async with client(handler) as c:
            await fetch_amazon.fetch_amazon(c, delay=0)
    with pytest.raises(RuntimeError, match=r"Amazon jobs API failed \d+ times at offset 100"):
        asyncio.run(go())


def test_goldman_sachs_raises_when_a_page_fails(monkeypatch):
    class Client:
        def __init__(self, *a, **k):
            self.calls = 0
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                items = [{"roleId": str(i), "jobTitle": "Analyst", "locations": [{"city": "Bengaluru", "country": "India"}]}
                         for i in range(100)]
                return httpx.Response(200, json={"data": {"roleSearch": {"items": items}}},
                                      request=httpx.Request("POST", "https://x"))
            return httpx.Response(500, request=httpx.Request("POST", "https://x"))
    monkeypatch.setattr(fetch_gs.httpx, "Client", Client)
    with pytest.raises(httpx.HTTPStatusError):
        fetch_gs.fetch_gs_jobs("Goldman Sachs")


def test_a_failing_source_is_marked_failed_and_its_jobs_stay_open(tmp_path, monkeypatch, profile_file):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [{
        "id": "s1", "company": "Swiggy", "title": "SDE", "location": "Bengaluru", "cities": ["Bengaluru"],
        "level": "Entry", "role": "Backend", "is_tech": 1, "employment_type": "Full-time", "description": "",
        "salary_text": "", "apply_url": "https://x/1", "source": "swiggy", "pay_verdict": "unknown",
        "score": 50, "score_reasons": []}], "2026-10-20T00:00:00Z")
    conn.close()

    async def broken(client, company):
        raise httpx.HTTPStatusError("402 Payment Required", request=httpx.Request("POST", "https://x"),
                                    response=httpx.Response(402))
    monkeypatch.setitem(pipeline.ADAPTERS, "swiggy", broken)
    asyncio.run(pipeline.run([{"name": "Swiggy", "ats": "swiggy"}], with_details=False))

    conn = db.connect()
    ok, error = conn.execute("SELECT ok, error FROM company_runs WHERE company='Swiggy'").fetchone()
    assert ok == 0 and "402" in error
    assert pipeline.health_status(bool(ok), 0, 0, None) == "failed"
    assert conn.execute("SELECT is_active FROM jobs WHERE id='s1'").fetchone()[0] == 1
