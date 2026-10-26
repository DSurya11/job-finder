"""Part 9: the LangGraph version keeps agent.py's checks. A scripted chat model stands in."""

import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from jobfinder import agent_lg, db  # noqa: E402


class ScriptedModel(BaseChatModel):
    """Answers with the next scripted tool call each time it is asked."""
    script: list
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        name, args = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        message = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{len(self.seen)}"}],
                            usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})
        return ChatResult(generations=[ChatGeneration(message=message)])


def _job(job_id, **kw):
    return {"id": job_id, "company": "Acme", "title": f"SRE {job_id}", "location": "Bengaluru",
            "cities": ["Bengaluru"], "level": "Entry", "role": "DevOps / SRE", "is_tech": 1,
            "employment_type": "Full-time", "description": "Kubernetes and Terraform.", "salary_text": "",
            "apply_url": f"https://example.com/{job_id}", "source": "greenhouse", "pay_verdict": "unknown",
            "score": 50, "score_reasons": [], **kw}


@pytest.fixture
def conn(tmp_path, monkeypatch, profile_file):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    conn = db.connect()
    db.upsert_jobs(conn, [_job("k1"), _job("k2")], "2026-10-24T00:00:00Z")
    return conn


def test_search_then_answer_gives_an_agent_result(conn):
    model = ScriptedModel(script=[("search_jobs", {"description_words": "kubernetes"}),
                                  ("give_answer", {"answer": "**2** jobs match.", "job_ids": ["k1"]})])
    result = agent_lg.ask("devops jobs", conn=conn, llm=model)
    assert (result.stopped, result.answer, result.job_ids, result.total_matching) == ("answered", "2 jobs match.", ["k1"], 2)
    assert [s["kind"] for s in result.steps] == ["model", "tool", "model", "answer"]


def test_an_invented_id_is_refused_and_the_model_told_why(conn):
    model = ScriptedModel(script=[("search_jobs", {"description_words": "kubernetes"}),
                                  ("give_answer", {"answer": "x", "job_ids": ["made-up"]}),
                                  ("give_answer", {"answer": "2 jobs.", "job_ids": ["k2"]})])
    result = agent_lg.ask("devops jobs", conn=conn, llm=model)
    assert result.job_ids == ["k2"]
    refused = [s for s in result.steps if s["kind"] == "tool" and s["tool"] == "give_answer"]
    assert refused and "made-up" in refused[0]["result"] and refused[0]["failed"]


def test_the_step_limit_still_holds(conn):
    model = ScriptedModel(script=[("search_jobs", {"description_words": "kubernetes"})])
    result = agent_lg.ask("devops jobs", conn=conn, llm=model, max_steps=3)
    assert result.stopped == "step_limit" and result.job_ids == ["k1", "k2"]
