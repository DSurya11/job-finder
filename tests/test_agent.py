"""The agent loop against a scripted fake model: free, and the same result every run."""

import json

import httpx
import pytest
from openai import APIConnectionError
from openai.types.chat import ChatCompletion

from jobfinder import agent, db


def _job(job_id: str, **kw) -> dict:
    base = {"id": job_id, "company": "Acme", "title": f"Engineer {job_id}", "location": "Bengaluru",
            "cities": ["Bengaluru"], "level": "Intern", "role": "DevOps / SRE", "is_tech": 1,
            "employment_type": "Internship", "description": "Kubernetes and Terraform.",
            "salary_text": "", "apply_url": f"https://example.com/{job_id}", "source": "greenhouse",
            "pay_verdict": "unknown", "score": 50, "score_reasons": []}
    return {**base, **kw}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("k1"), _job("k2", title="SRE intern")], "2026-10-12T00:00:00Z")
    return conn


def reply(*calls, text=None, prompt_tokens=100):
    """One model response: tool calls given as (name, arguments) pairs, or plain text."""
    return ChatCompletion.model_validate({
        "id": "r", "object": "chat.completion", "created": 0, "model": "fake-model",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {
            "role": "assistant", "content": text,
            "tool_calls": [{"id": f"call{i}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}
                           for i, (name, args) in enumerate(calls)] or None}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 10,
                  "total_tokens": prompt_tokens + 10},
    })


class FakeClient:
    """Stands in for the OpenAI client: returns scripted replies, records every request."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []
        self.chat = self
        self.completions = self

    def create(self, **request):
        self.requests.append(json.loads(json.dumps(request["messages"])))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step

    def last_tool_result(self, request: int) -> str:
        return [m for m in self.requests[request] if m["role"] == "tool"][-1]["content"]


SEARCH = ("search_jobs", {"description_words": "kubernetes"})


def test_search_then_answer(conn):
    fake = FakeClient(reply(SEARCH), reply(("give_answer", {"answer": "Two.", "job_ids": ["k2", "k1"]})))
    result = agent.ask("kubernetes internships?", conn=conn, client=fake)
    assert (result.stopped, result.answer, result.job_ids) == ("answered", "Two.", ["k2", "k1"])
    assert len(fake.requests) == 2
    assert result.tokens_in == 200


def test_an_invented_id_is_rejected_and_the_model_corrects_itself(conn):
    fake = FakeClient(
        reply(SEARCH),
        reply(("give_answer", {"answer": "Here.", "job_ids": ["k1", "made-up"]})),
        reply(("give_answer", {"answer": "Here.", "job_ids": ["k1"]})),
    )
    result = agent.ask("q", conn=conn, client=fake)
    assert "not returned by any tool in this conversation: ['made-up']" in fake.last_tool_result(2)
    assert (result.stopped, result.job_ids) == ("answered", ["k1"])


def test_the_step_limit_returns_what_was_found(conn):
    fake = FakeClient(reply(SEARCH))                    # searches forever
    result = agent.ask("q", conn=conn, client=fake, max_steps=3)
    assert result.stopped == "step_limit"
    assert len(fake.requests) == 3
    assert sorted(result.job_ids) == ["k1", "k2"]
    assert "step limit of 3" in result.answer


def test_a_tool_error_goes_back_to_the_model(conn):
    fake = FakeClient(
        reply(("search_jobs", {"levels": ["Junior"]})),
        reply(("search_jobs", {"levels": ["Intern"]})),
        reply(("give_answer", {"answer": "Found.", "job_ids": ["k1"]})),
    )
    result = agent.ask("q", conn=conn, client=fake)
    assert "unknown levels ['Junior']" in fake.last_tool_result(1)
    assert result.stopped == "answered"
    assert [s["failed"] for s in result.steps if s["kind"] == "tool"] == [True, False]


def test_plain_text_is_asked_again_for_give_answer(conn):
    fake = FakeClient(reply(text="Probably two jobs."), reply(SEARCH),
                      reply(("give_answer", {"answer": "Two.", "job_ids": ["k1"]})))
    result = agent.ask("q", conn=conn, client=fake)
    assert fake.requests[1][-1]["content"].startswith("Finish by calling give_answer")
    assert result.stopped == "answered"


def test_a_service_failure_returns_partial_results_instead_of_crashing(conn):
    down = APIConnectionError(request=httpx.Request("POST", "http://127.0.0.1:20130/v1/chat/completions"))
    fake = FakeClient(reply(SEARCH), down)
    result = agent.ask("q", conn=conn, client=fake)
    assert result.stopped == "error"
    assert sorted(result.job_ids) == ["k1", "k2"]


def test_the_token_budget_stops_the_loop(conn):
    fake = FakeClient(reply(SEARCH, prompt_tokens=agent.MAX_INPUT_TOKENS))
    result = agent.ask("q", conn=conn, client=fake)
    assert result.stopped == "token_budget"
    assert len(fake.requests) == 1
