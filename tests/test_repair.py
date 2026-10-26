"""Coverage repair against a scripted model and fake boards: proposals are proved by code, and
only an approval changes companies.yaml."""

import json

import pytest
import yaml
from openai.types.chat import ChatCompletion

from jobfinder import agent_tools, db, pipeline, repair


def reply(*calls):
    return ChatCompletion.model_validate({
        "id": "r", "object": "chat.completion", "created": 0, "model": "fake-model",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                           for i, (n, a) in enumerate(calls)]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}})


class FakeClient:
    def __init__(self, *script):
        self.script, self.requests = list(script), []
        self.chat = self
        self.completions = self

    def create(self, **request):
        self.requests.append(request["messages"])
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


BOARDS = {("lever", "acme-new"): {"total": 40, "india": 12, "sample_titles": ["SRE, Bengaluru"]},
          ("greenhouse", "acme-us"): {"total": 30, "india": 0, "sample_titles": ["SRE, Austin"]}}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    companies = tmp_path / "companies.yaml"
    companies.write_text(yaml.safe_dump({"companies": [
        {"name": "Acme", "ats": "lever", "slug": "acme-old", "careers_url": "https://acme.com/careers", "enabled": True},
        {"name": "Other", "ats": "greenhouse", "slug": "other", "enabled": True}]}, sort_keys=False))
    monkeypatch.setattr(pipeline, "COMPANIES_PATH", companies)

    def fake_probe(config, name):
        key = (config["ats"], config.get("slug"))
        if key not in BOARDS:
            raise agent_tools.ToolError("the board answered HTTP 404")
        return BOARDS[key]
    monkeypatch.setattr(repair, "probe", fake_probe)
    conn = db.connect()
    conn.execute("INSERT INTO runs (id, started) VALUES (1, '2026-10-25T00:00:00Z')")
    for company, ats, raw, india, ok in (("Acme", "lever", 0, 0, 1), ("Other", "greenhouse", 50, 20, 1)):
        conn.execute("INSERT INTO company_runs (run_id, company, ats, ok, raw_count, india_count, error) "
                     "VALUES (1, ?, ?, ?, ?, ?, '')", (company, ats, ok, raw, india))
    conn.commit()
    return conn, companies


def test_only_broken_companies_with_unchanged_settings_are_investigated(setup):
    conn, _ = setup
    assert [b["company"] for b in repair.broken_companies(conn)] == ["Acme"]


def test_a_proposal_is_proved_by_code_and_waits_for_approval(setup):
    conn, companies = setup
    broken = repair.broken_companies(conn)[0]
    client = FakeClient(reply(("try_board", {"ats": "lever", "slug": "acme-new"})),
                        reply(("propose_fix", {"ats": "lever", "slug": "acme-new", "evidence": "careers page links it"})))
    outcome = repair.investigate(conn, broken, client)
    assert outcome.result == "proposed"
    [p] = repair.proposals(conn)
    assert (p["status"], p["india_jobs"], p["proposed"]) == ("pending", 12, {"ats": "lever", "slug": "acme-new"})
    assert "acme-old" in companies.read_text()                       # nothing applied yet
    assert repair.broken_companies(conn) == []                       # not investigated twice


def test_a_board_without_india_jobs_is_rejected_by_code_whatever_the_model_says(setup):
    conn, _ = setup
    client = FakeClient(reply(("propose_fix", {"ats": "greenhouse", "slug": "acme-us", "evidence": "same name"})))
    assert repair.investigate(conn, repair.broken_companies(conn)[0], client).result == "rejected_by_check"
    assert repair.proposals(conn)[0]["status"] == "rejected_by_check"


def test_approval_is_the_only_path_that_edits_companies_yaml(setup):
    conn, companies = setup
    client = FakeClient(reply(("propose_fix", {"ats": "lever", "slug": "acme-new", "evidence": "x"})))
    pid = repair.investigate(conn, repair.broken_companies(conn)[0], client).proposal_id
    repair.decide(conn, pid, approve=True, fetch=False)
    acme = next(c for c in yaml.safe_load(companies.read_text())["companies"] if c["name"] == "Acme")
    assert acme == {"name": "Acme", "ats": "lever", "slug": "acme-new", "careers_url": "https://acme.com/careers",
                    "enabled": True}
    with pytest.raises(ValueError):
        repair.decide(conn, pid, approve=True, fetch=False)          # decided once only


def test_a_rejection_changes_nothing_but_the_proposal(setup):
    conn, companies = setup
    before = companies.read_text()
    client = FakeClient(reply(("propose_fix", {"ats": "lever", "slug": "acme-new", "evidence": "x"})))
    pid = repair.investigate(conn, repair.broken_companies(conn)[0], client).proposal_id
    assert repair.decide(conn, pid, approve=False) == {"status": "rejected"}
    assert companies.read_text() == before


def test_switching_to_workday_removes_the_old_boards_fields(setup):
    conn, companies = setup
    BOARDS[("workday", None)] = {"total": 500, "india": 80, "sample_titles": []}
    client = FakeClient(reply(("propose_fix", {"ats": "workday", "tenant": "acme", "wd_instance": "wd5",
                                               "site": "AcmeCareers", "evidence": "x"})))
    pid = repair.investigate(conn, repair.broken_companies(conn)[0], client).proposal_id
    repair.decide(conn, pid, approve=True, fetch=False)
    acme = next(c for c in yaml.safe_load(companies.read_text())["companies"] if c["name"] == "Acme")
    assert "slug" not in acme and acme["tenant"] == "acme" and acme["site"] == "AcmeCareers"


def test_no_fix_and_the_daily_cap(setup, monkeypatch):
    conn, _ = setup
    outcome = repair.investigate(conn, repair.broken_companies(conn)[0], FakeClient(reply(("no_fix", {"reason": "no board"}))))
    assert outcome.result == "no_fix" and repair.proposals(conn)[0]["status"] == "no_fix"
    calls = []
    monkeypatch.setattr(repair, "broken_companies", lambda conn: [{"company": f"C{i}", "config": {}} for i in range(9)])
    monkeypatch.setattr(repair, "investigate", lambda conn, b, client: calls.append(b) or repair.Outcome(b["company"], "no_fix"))
    repair.run(client=object())
    assert len(calls) == repair.MAX_COMPANIES


def test_board_links_are_read_by_code():
    html = ('<a href="https://boards.greenhouse.io/embed/job_board?for=acme">jobs</a> '
            '<a href="https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers">Workday</a> jobs.lever.co/acme')
    assert repair.board_links(html) == [
        {"ats": "greenhouse", "slug": "acme"}, {"ats": "lever", "slug": "acme"},
        {"ats": "workday", "tenant": "acme", "wd_instance": "wd5", "site": "AcmeCareers"}]


def test_a_refused_call_repeated_ends_as_stuck_and_is_recorded(setup):
    # Measured: the same refused find_board_links call six times until the steps ran out.
    conn, _ = setup
    same = ("find_board_links", {"url": "https://evil.example/careers"})
    outcome = repair.investigate(conn, repair.broken_companies(conn)[0], FakeClient(reply(same)))
    assert (outcome.result, outcome.note) == ("no_fix", "stuck repeating a refused find_board_links call")
    assert repair.proposals(conn)[0]["status"] == "no_fix"
    assert repair.broken_companies(conn) == []                       # not retried for a week


def test_without_a_careers_page_the_companys_own_named_site_may_be_read(monkeypatch):
    called = []
    monkeypatch.setattr(repair.httpx.Client, "get", lambda self, url: called.append(url) or (_ for _ in ()).throw(repair.httpx.ConnectError("offline")))
    with pytest.raises(agent_tools.ToolError, match="could not fetch"):
        repair._find_links("https://www.fimoney.com/careers", [], "fimoney")    # allowed: fetched
    with pytest.raises(agent_tools.ToolError, match="not the company's own site"):
        repair._find_links("https://www.example.com/fimoney", [], "fimoney")    # name only in the path
    assert called == ["https://www.fimoney.com/careers"]


def test_guess_boards_tries_the_name_on_every_simple_board(monkeypatch):
    async def lever(client, co):
        if co["slug"] == "citadelsecurities":
            return [{"title": "SRE", "location": "Bengaluru, India"}, {"title": "Dev", "location": "London"}]
        raise repair.httpx.HTTPStatusError("404", request=None, response=None)
    async def nothing(client, co):
        return []
    monkeypatch.setattr(repair, "ADAPTERS", {b: (lever if b == "lever" else nothing) for b in repair.SIMPLE_BOARDS})
    assert repair.guess("Citadel Securities", {}) == [
        {"ats": "lever", "slug": "citadelsecurities", "total": 2, "india": 1, "sample_titles": ["SRE", "Dev"]}]
    assert repair.guess("Nobody Inc", {})[0]["result"].startswith("no board answered")
