"""Part 9: the Ask agent rebuilt on LangGraph's prebuilt ReAct agent, to compare with agent.py.

Same tools (agent_tools), same system prompt, same model through OmniRoute, same checks: the id
check (give_answer refuses ids no tool returned, and the model is told why), the step limit,
the code-stated description-filter fact and plain-text answers. What differs is the loop:
LangGraph runs it instead of the ~120 lines in agent._loop. The result has agent.Result's shape,
so the evals score both alike:

    python -m jobfinder eval --impl langgraph

Optional dependency (requirements-langgraph.txt); the app itself does not use it.
LangSmith tracing stays off: nothing leaves except the model calls.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import date

os.environ.setdefault("LANGSMITH_TRACING", "false")

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.tools import StructuredTool, ToolException  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402
from langgraph.prebuilt import ToolNode, create_react_agent  # noqa: E402
from openai import APIError, RateLimitError  # noqa: E402

from . import agent, agent_tools, db  # noqa: E402


class _Answered(Exception):
    """Raised by give_answer once its ids pass the check: stops the graph with the answer."""

    def __init__(self, payload: dict):
        super().__init__("answered")
        self.payload = payload


def ask(question: str, conn: sqlite3.Connection | None = None, client=None, model: str = agent.MODEL,
        max_steps: int = agent.MAX_STEPS, source: str = "cli", cache: bool = True, llm=None) -> agent.Result:
    """llm: a LangChain chat model; tests pass a scripted one. Default: OmniRoute via ChatOpenAI."""
    started, started_at = time.monotonic(), db.now()
    own = conn is None
    conn = conn or db.connect()
    try:
        result = _run(question, conn, model, max_steps, cache, started, llm)
        agent.save_run(conn, question, result, source + "-langgraph", started_at)
        return result
    finally:
        if own:
            conn.close()


def _run(question: str, conn: sqlite3.Connection, model: str, max_steps: int, cache: bool,
         started: float, llm=None) -> agent.Result:
    seen: list[str] = []
    last: dict = {}
    path = conn.execute("PRAGMA database_list").fetchone()[2]

    def tool(name: str, schema: dict) -> StructuredTool:
        function = agent_tools.FUNCTIONS[name]

        def call(**arguments) -> str:
            # LangGraph runs tools on worker threads, and a SQLite connection belongs to the thread
            # that made it (first live run: "SQLite objects created in a thread can only be used in
            # that same thread"). Each call opens its own, on the same database file.
            local = db.connect(path)
            try:
                text = function(local, **arguments)
            except (agent_tools.ToolError, TypeError) as error:
                raise ToolException(f"ERROR: {error}")
            finally:
                local.close()
            seen.extend(i for i in agent._ids_in(text) if i not in seen)
            if name == "search_jobs":
                last.update(found=json.loads(text), arguments=arguments)
            return text
        return StructuredTool.from_function(func=call, name=name, description=schema["description"],
                                            args_schema=schema["parameters"], handle_tool_error=True)

    def give_answer(answer: str, job_ids: list[str]) -> str:
        unknown = [i for i in job_ids if i not in seen]
        if unknown:                           # the id check, told to the model like agent.py does
            raise ToolException(f"ERROR: these ids were not returned by any tool in this conversation: "
                                f"{unknown}. Use only ids from tool results.")
        # A checked answer ends the run from inside. return_direct=True was tried first: LangGraph
        # then ended the run even when the id check refused, so the model could never correct it.
        raise _Answered({"answer": answer, "job_ids": job_ids})

    schemas = {s["function"]["name"]: s["function"] for s in agent_tools.schemas(conn)}
    tools = [tool(name, schema) for name, schema in schemas.items()]
    tools.append(StructuredTool.from_function(
        func=give_answer, name="give_answer", description=agent.GIVE_ANSWER["function"]["description"],
        args_schema=agent.GIVE_ANSWER["function"]["parameters"], handle_tool_error=True))

    llm = llm or ChatOpenAI(base_url=agent.BASE_URL, api_key=os.getenv("OMNIROUTE_API_KEY"), model=model,
                            temperature=0, timeout=agent.TIMEOUT_SECONDS, max_retries=agent.CLIENT_RETRIES,
                            default_headers=None if cache else {"x-omniroute-no-cache": "true"})
    fetched = (conn.execute("SELECT MAX(last_seen) FROM jobs").fetchone()[0] or "never")[:10]
    # Only ToolException becomes a message for the model; _Answered must get out of the graph.
    node = ToolNode(tools, handle_tool_errors=(ToolException,))
    graph = create_react_agent(llm, node, prompt=agent.SYSTEM.format(today=date.today().isoformat(),
                                                                     fetched=fetched))
    result = agent.Result(answer="", job_ids=[], stopped="")
    messages: list = []
    answered: dict | None = None
    try:
        # One model call and one tool round per step, plus the final answer.
        for state in graph.stream({"messages": [("user", question)]}, stream_mode="values",
                                  config={"recursion_limit": 2 * max_steps + 1}):
            messages = state["messages"]
        stopped = "no_answer"
    except _Answered as done:
        answered, stopped = done.payload, "answered"
    except GraphRecursionError:
        stopped = "step_limit"
    except APIError as error:
        stopped = "error"
        result.steps.append({"step": 0, "kind": "error", "error": str(error)[:300],
                             "rate_limited": isinstance(error, RateLimitError)})

    _trace(messages, result)
    if answered is not None:
        result.steps.append({"step": len([s for s in result.steps if s["kind"] == "model"]), "kind": "answer",
                             "job_ids": answered["job_ids"]})
        result.answer = re.sub(r"\*\*|__|^#+\s*", "", answered["answer"], flags=re.M)
        result.job_ids = answered["job_ids"][:agent.MAX_JOBS]
    else:
        result.job_ids = seen[:agent.MAX_JOBS]
        result.answer = f"I stopped before finishing ({stopped.replace('_', ' ')})."
    if last:
        found = last["found"]
        result.total_matching = found["total_matching"]
        result.search = {k: v for k, v in last["arguments"].items() if k not in ("sort", "limit")}
        if stopped == "answered" and "without_description_filter" in found:
            words = [result.search.get("description_words") or "", *(result.search.get("description_any") or [])]
            result.answer += (f"\n\n{found['without_description_filter']} jobs match without the description "
                              f"filter ({', '.join(chr(34) + w + chr(34) for w in words if w)}); the {found['total_matching']} "
                              f"above also mention those words.")
    result.stopped, result.seconds = stopped, round(time.monotonic() - started, 2)
    return result


def _trace(messages: list, result: agent.Result) -> None:
    """The run as agent.Result steps, so the evals read both implementations the same way."""
    step = 0
    for m in messages:
        if isinstance(m, AIMessage):
            step += 1
            usage = m.usage_metadata or {}
            result.tokens_in += usage.get("input_tokens", 0)
            result.tokens_out += usage.get("output_tokens", 0)
            result.steps.append({"step": step, "kind": "model", "model": m.response_metadata.get("model_name"),
                                 "tokens_in": usage.get("input_tokens"), "tokens_out": usage.get("output_tokens")})
            calls = {c["id"]: c for c in m.tool_calls}
            result.steps[-1]["calls"] = list(calls)
        elif isinstance(m, ToolMessage):
            content = str(m.content)
            if m.name == "give_answer" and not content.startswith("ERROR"):
                result.steps.append({"step": step, "kind": "answer"})
                continue
            arguments = next((json.dumps(c["args"]) for s in messages if isinstance(s, AIMessage)
                              for c in s.tool_calls if c["id"] == m.tool_call_id), "{}")
            result.steps.append({"step": step, "kind": "tool", "tool": m.name, "arguments": arguments,
                                 "failed": m.status == "error" or content.startswith("ERROR"),
                                 "result": content[:300]})
